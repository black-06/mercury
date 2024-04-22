run:
	cd src && uvicorn main:app --reload --host 0.0.0.0 --port 3333

init:
	docker compose up -d

update_env:
	conda env export > environment.yml

build:
	docker build -t mercury .

restart:
	docker compose down && docker compose up -d