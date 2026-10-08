FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /app

# Install dependencies straight from pyproject.toml (runtime + dev, so tests run in the container).
COPY pyproject.toml ./
RUN python -c "import tomllib; p = tomllib.load(open('pyproject.toml','rb'))['project']; \
print('\n'.join(p['dependencies'] + p['optional-dependencies']['dev']))" > /tmp/requirements.txt \
 && pip install -r /tmp/requirements.txt && rm /tmp/requirements.txt

RUN useradd --create-home --uid 1000 app && chown app:app /app
COPY --chown=app:app main.py ./
COPY --chown=app:app src ./src
COPY --chown=app:app tests ./tests
COPY --chown=app:app scripts ./scripts
RUN mkdir -p resumes output && chown app:app resumes output
USER app

# Secrets come from --env-file / the environment at run time, never from the image.
CMD ["python", "main.py", "--help"]
