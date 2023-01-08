FROM python:3.10.7-slim-buster
RUN apt update && apt install -y build-essential
RUN pip3 install poetry
COPY dist/etymmap-0.1.0-py3-none-any.whl /dist/
COPY frontend/pyproject.toml frontend/poetry.lock /frontend/
COPY frontend/assets /frontend/assets
COPY frontend/explorer /frontend/explorer
WORKDIR frontend
RUN poetry config virtualenvs.create false
RUN poetry install --only main
EXPOSE 8050
# CMD poetry run python explorer/main.py
