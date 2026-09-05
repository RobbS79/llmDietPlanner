"""Fixed prompts for the Friday plan showcase. Each is a realistic Czech
request from a target persona (docs/persona-test-prompts.md); the pipeline
rotates by absolute week index so no prompt repeats week-to-week. Keep them
honest to what the product does well."""

from .weeks import week_start

PERSONA_PROMPTS = [
    # Time-Pressed Couple
    'Vaříme pro dva, večer chceme něco rychlého do 30 minut, bez ryb.',
    # Budget Family
    'Rodina se dvěma dětmi, chceme levně a jednoduše, klasická česká kuchyně.',
    # Fitness
    'Chci zhubnout, hodně bílkovin, snídaně a večeře lehké, oběd sytý.',
]


def persona_for_week(iso: str) -> str:
    return PERSONA_PROMPTS[week_start(iso).toordinal() // 7 % len(PERSONA_PROMPTS)]
