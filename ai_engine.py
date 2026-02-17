import json
import os
import re

import anthropic

from app import db
from models import WorkoutPlan, WorkoutDay, Exercise, WorkoutLog

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

PROGRESSIVE OVERLOAD — this is week {week_number}. Here is last week's plan WITH actual logged performance data (if available):
{json.dumps(previous_plan, indent=2)}

Apply progressive overload based on ACTUAL performance:
- If actual_reps and actual_weight_kg are provided, use those to determine progression (not just prescribed values)
- If the user hit or exceeded prescribed reps at the prescribed weight, increase weight by 2.5kg
- If the user fell short of prescribed reps, keep the same weight but adjust reps
- For accessories: add 1 rep or slightly increase weight based on actual performance
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


def plan_to_dict_with_logs(plan, user_id):
    """Convert a WorkoutPlan to a dict that includes actual logged performance data."""
    exercise_ids = []
    for day in plan.days:
        for ex in day.exercises:
            exercise_ids.append(ex.id)

    logs = WorkoutLog.query.filter(
        WorkoutLog.exercise_id.in_(exercise_ids),
        WorkoutLog.user_id == user_id,
    ).all()
    log_map = {log.exercise_id: log for log in logs}

    result = []
    for day in plan.days:
        day_data = {
            "day_index": day.day_index,
            "label": day.label,
            "exercises": [],
        }
        for ex in day.exercises:
            ex_data = {
                "name": ex.name,
                "prescribed_sets": ex.sets,
                "prescribed_reps": ex.reps,
                "prescribed_weight_kg": ex.weight_kg,
                "is_compound": ex.is_compound,
                "notes": ex.notes or "",
            }
            log = log_map.get(ex.id)
            if log:
                ex_data["actual_reps"] = log.actual_reps
                ex_data["actual_weight_kg"] = log.actual_weight_kg
            day_data["exercises"].append(ex_data)
        result.append(day_data)
    return result


def chat_with_ai(message, plan, profile):
    """Send a chat message to Claude with the user's plan context. Returns reply text and optionally a modified plan."""
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise ValueError("ANTHROPIC_API_KEY environment variable is not set.")

    client = anthropic.Anthropic(api_key=api_key)

    plan_dict = plan_to_dict(plan) if plan else []
    plan_type_desc = PLAN_TYPE_LABELS.get(profile.plan_type, profile.plan_type) if profile else "Unknown"
    goal_desc = GOAL_LABELS.get(profile.goal, profile.goal) if profile else "Unknown"

    system_prompt = f"""You are ForgeFit AI, a knowledgeable personal trainer assistant. The user has an active workout plan.

User profile:
- Height: {profile.height_cm}cm, Weight: {profile.weight_kg}kg
- Goal: {goal_desc}
- Plan type: {plan_type_desc}
- 1RM - Squat: {profile.squat_1rm}kg, Bench: {profile.bench_1rm}kg, Deadlift: {profile.deadlift_1rm}kg, OHP: {profile.ohp_1rm}kg

Current plan (Week {plan.week_number}):
{json.dumps(plan_dict, indent=2)}

Instructions:
- Answer fitness questions helpfully and concisely.
- If the user asks to MODIFY their plan (e.g. "make squats heavier", "swap bench for incline press", "add more arm work"), return the FULL modified plan as a JSON array at the end of your reply, wrapped in <plan_json>...</plan_json> tags.
- The JSON must follow the exact same format as the current plan shown above.
- If the user is just chatting or asking questions (not requesting changes), do NOT include plan JSON.
- Keep responses concise (2-4 sentences max for conversational replies)."""

    response = client.messages.create(
        model="claude-sonnet-4-5-20250929",
        max_tokens=4096,
        system=system_prompt,
        messages=[{"role": "user", "content": message}],
    )

    reply_text = response.content[0].text.strip()

    # Check if reply contains a modified plan
    plan_data = None
    import re as _re
    match = _re.search(r"<plan_json>(.*?)</plan_json>", reply_text, _re.DOTALL)
    if match:
        try:
            plan_json_str = match.group(1).strip()
            plan_json_str = _re.sub(r"^```(?:json)?\s*", "", plan_json_str)
            plan_json_str = _re.sub(r"\s*```$", "", plan_json_str)
            plan_data = json.loads(plan_json_str)
        except (json.JSONDecodeError, ValueError):
            plan_data = None
        # Remove the plan JSON from the visible reply
        reply_text = reply_text[:match.start()].strip()

    return reply_text, plan_data
