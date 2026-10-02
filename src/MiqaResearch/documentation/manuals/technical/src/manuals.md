(heading-manuals)=
# The manuals

The User Manual and this Technical Manual are written in MyST Markdown under
`documentation/manuals/<manual>/` and built by Sphinx into JSON. The app renders that JSON
inside its own pages, so Sphinx never runs in production.

(heading-manuals-build)=
## Building

`documentation/build_manuals.py` builds every manual, in English plus each language that has a
`locale/<lang>/` directory, into `MANUALS_BUILD_DIR` (`documentation/builds/<manual>/<lang>/`).
It needs the `docs` uv group, which `dev` includes.

```sh
uv run python documentation/build_manuals.py            # strict: any Sphinx warning fails
uv run python documentation/build_manuals.py --no-strict # local drafts
```

When a manual has no English build, Django's system checks warn at startup
(`documentation.W001`) and its pages return 404.

(heading-manuals-dev-loop)=
## Writing with the dev stack

With the dev containers running, rebuild the affected manual on every save and reload the page
in the app to see the change:

```sh
docker compose exec mires_web python documentation/build_manuals.py --watch
```

(heading-manuals-docker)=
## Production image

The prod `Dockerfile` builds the manuals in a separate `docs` stage (strict, so a Sphinx
warning fails the image build) and copies only the builds into the final image, which has no
Sphinx installed. The manuals therefore always match the app version in the image.
