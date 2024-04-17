run:
	cd src && uvicorn main:app --reload --host 0.0.0.0

init:
	docker compose up -d