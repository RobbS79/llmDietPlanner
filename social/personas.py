"""Fixed prompts for the Friday plan showcase. Each is a realistic Czech
request from a target persona (docs/persona-test-prompts.md); the pipeline
rotates through them by ISO week number so the same one is not shown twice
in a row. Keep them honest to what the product does well."""

PERSONA_PROMPTS = [
    # Time-Pressed Couple
    'Vaříme pro dva, večer chceme něco rychlého do 30 minut, bez ryb.',
    # Budget Family
    'Rodina se dvěma dětmi, chceme levně a jednoduše, klasická česká kuchyně.',
    # Fitness
    'Chci zhubnout, hodně bílkovin, snídaně a večeře lehké, oběd sytý.',
]


def persona_for_week(iso_week: str) -> str:
    week_number = int(iso_week.split('-W')[1])
    return PERSONA_PROMPTS[week_number % len(PERSONA_PROMPTS)]
