# Photolike photography skill

Plan a compatible high-end camera kit and a practical next-photo exercise using Photolike's public, read-only reference API. The helper needs only Python 3 and network access. It does not render images, upload photographs, accept API keys, or access accounts.

## Install

```sh
npx skills add Manny4C/photolike-agent-skill --skill photolike-photography
```

The installation command uses the skills CLI and its Node.js requirements. Once installed, the bundled helper itself has no third-party Python dependencies. Ask your agent to use `photolike-photography` to check a native camera/lens combination or prepare a sourced shooting brief.

## Helper

From the installed skill directory (the folder containing `SKILL.md`):

```sh
python3 scripts/photolike.py catalog
python3 scripts/photolike.py kit sony-a7r-v sony-fe-85
python3 scripts/photolike.py recipe sony
python3 scripts/photolike.py brief sony
```

For a checkout of this repository, first enter `skills/photolike-photography/`.

`brief` fetches the chosen recipe and its native kit check, refuses an incompatible kit, and returns the actual practical exercise, sources and dates. Its simulated look and listed kit aperture are kept separate from the exercise. Settings are a starting point for discussion, not a metered exposure prescription. Use the person's actual lens, light, movement and photographic intent when adapting the exercise.

## Testing and measurement

All our QA, demos and internal checks use `--test`, before or after the command:

```sh
python3 scripts/photolike.py --test brief sony
```

Requests carry `X-Photolike-Agent: 1` and `X-Photolike-Channel: photolike-skill`; `--test` also sends `X-Photolike-Test: 1`. Only selected catalog IDs are sent, never photos, conversation text, prompts or credentials. The helper makes bounded JSON GET requests to the fixed HTTPS Photolike origin and rejects redirects. It writes no files or configuration.

Photolike records aggregate requests, not verified independent agents or completed jobs. Our installations and test traffic are internal verification, not independent adoption. See the [public agent guide](https://photolike-nine.vercel.app/agents.md) for measurement and privacy details.

Run offline helper tests from this repository root:

```sh
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -v
```

## Sources and limits

The catalog is curated, with source links and verification dates; it is not live inventory, pricing or a purchasing recommendation. Follow manufacturer sources for current decisions. Native compatibility excludes adapters. Camera-inspired looks are creative interpretations, not measured hardware performance. Keep people, appearance, clothing and the real scene faithful; imagined viewpoints cannot verify hidden detail.

This package contains instructions and a small API client. The MIT license covers this package only. It grants no rights to Photolike site media, third-party photography, trademarks or linked source material. No payment or tipping capability is included.
