FROM python:3.10.7-slim-buster
RUN pip3 install poetry
# copy everything to app/
COPY pyproject.toml poetry.lock /app/
COPY etymmap/etymmap-0.1.0-py3-none-any.whl /app/etymmap/
COPY assets /app/assets
COPY explorer /app/explorer
WORKDIR app
RUN poetry config virtualenvs.create false
# todo fix install failure
RUN poetry install --only main
EXPOSE 8050
CMD poetry run explorer/main.py
