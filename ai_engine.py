import json
import os
import re

import anthropic

from app import db
from models import WorkoutPlan, WorkoutDay, Exercise

PLAN_TYPE_LABELS = {
    "push_pull_legs": "Push / Pull / Legs",
    "upper_lower": "Upper / Lower",
    "full_body": "Full Body",
    "menstrual_cycle": "Menstrual Cycle Adapted",
    "bro_split": "Bro Split",
}

GOAL_LABELS = {
    "muscle": "Build Muscle (hypertrophy — moderate weight, higher reps)",
    "strength": "Get Stronger (heavy weight, lower reps)",
    "general": "General Fitness (balanced approach)",
}

PLAN_TYPE_INSTRUCTIONS = {
    "push_pull_legs": "Structure the days as Push (chest, shoulders, triceps), Pull (back, biceps), and Legs. For 4-5 days, repeat the split.",
    "upper_lower": "Alternate between Upper Body and Lower Body days.",
    "full_body": "Each day should hit all major muscle groups with compound movements.",
    "menstrual_cycle": (
        "Design a training plan that adapts to the menstrual cycle phases. "
        "Week 1-2 (follicular phase): higher intensity and volume. "
        "Week 3 (ovulation): moderate intensity. "
        "Week 4 (luteal phase): lighter deload week with reduced volume. "
        "For this specific week number, adjust intensity accordingly."
    ),
    "bro_split": "Each day focuses on one muscle group: Chest, Back, Shoulders, Legs, Arms. Adjust for the number of days available.",
}


def generate_plan_with_ai(profile_data, week_number, previous_plan=None):
    """Call Claude API to generate a structured workout plan."""
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise ValueError("ANTHROPIC_API_KEY environment variable is not set.")

    client = anthropic.Anthropic(api_key=api_key)

    goal_desc = GOAL_LABELS.get(profile_data["goal"], profile_data["goal"])
    plan_type_desc = PLAN_TYPE_LABELS.get(profile_data["plan_type"], profile_data["plan_type"])
    plan_type_instr = PLAN_TYPE_INSTRUCTIONS.get(profile_data["plan_type"], "")

    prompt = f"""Generate a {profile_data['days_per_week']}-day weekly workout plan.

User profile:
- Height: {profile_data['height_cm']}cm
- Weight: {profile_data['weight_kg']}kg
- Goal: {goal_desc}
- Plan type: {plan_type_desc}
- 1RM - Squat: {profile_data['squat_1rm']}kg, Bench Press: {profile_data['bench_1rm']}kg, Deadlift: {profile_data['deadlift_1rm']}kg, Overhead Press: {profile_data['ohp_1rm']}kg

Plan type instructions: {plan_type_instr}

This is WEEK {week_number}.

Requirements:
- Each day must include compound movements plus accessory/isolation work (5-8 exercises per day)
- Calculate working weights as percentages of the user's 1RM for compound lifts
- Round all weights to the nearest 2.5kg
- Include appropriate sets and reps for the user's goal
- Mark compound movements as is_compound: true"""

    if previous_plan and week_number > 1:
        prompt += f"""

PROGRESSIVE OVERLOAD — this is week {week_number}. Here is last week's plan:
{json.dumps(previous_plan, indent=2)}

Apply progressive overload:
- For compound lifts: increase weight by 2.5kg OR add 1 rep per set (alternate as appropriate)
- For accessories: add 1 rep or slightly increase weight
- Keep the same exercise structure and day labels"""

    prompt += """

Return ONLY valid JSON — no markdown, no explanation. Use this exact format:
[
  {
    "day_index": 0,
    "label": "Day Name",
    "exercises": [
      {"name": "Exercise Name", "sets": 4, "reps": 8, "weight_kg": 70.0, "is_compound": true, "notes": ""},
      {"name": "Exercise Name", "sets": 3, "reps": 12, "weight_kg": 20.0, "is_compound": false, "notes": ""}
    ]
  }
]"""

    message = client.messages.create(
        model="claude-sonnet-4-5-20250929",
        max_tokens=4096,
        system="You are an expert certified personal trainer and strength coach. Generate structured workout plans as JSON only. No explanations, no markdown fences — just the JSON array.",
        messages=[{"role": "user", "content": prompt}],
    )

    response_text = message.content[0].text.strip()

    # Strip markdown code fences if present
    response_text = re.sub(r"^```(?:json)?\s*", "", response_text)
    response_text = re.sub(r"\s*```$", "", response_text)

    plan_data = json.loads(response_text)

    if not isinstance(plan_data, list):
        raise ValueError("AI response was not a JSON array")

    return plan_data


def save_plan_to_db(user_id, week_number, plan_data):
    """Save a generated plan to the database."""
    plan = WorkoutPlan(user_id=user_id, week_number=week_number)
    db.session.add(plan)
    db.session.flush()  # Get plan.id

    for day_data in plan_data:
        day = WorkoutDay(
            plan_id=plan.id,
            day_index=day_data["day_index"],
            label=day_data["label"],
        )
        db.session.add(day)
        db.session.flush()

        for i, ex_data in enumerate(day_data.get("exercises", [])):
            exercise = Exercise(
                day_id=day.id,
                order=i,
                name=ex_data["name"],
                sets=int(ex_data["sets"]),
                reps=int(ex_data["reps"]),
                weight_kg=float(ex_data["weight_kg"]),
                is_compound=bool(ex_data.get("is_compound", False)),
                notes=ex_data.get("notes", ""),
            )
            db.session.add(exercise)

    db.session.commit()


def plan_to_dict(plan):
    """Convert a WorkoutPlan model to a dict for passing to the AI."""
    return [
        {
            "day_index": day.day_index,
            "label": day.label,
            "exercises": [
                {
                    "name": ex.name,
                    "sets": ex.sets,
                    "reps": ex.reps,
                    "weight_kg": ex.weight_kg,
                    "is_compound": ex.is_compound,
                    "notes": ex.notes or "",
                }
                for ex in day.exercises
            ],
        }
        for day in plan.days
    ]
