.PHONY: test health verify-binaries sync-skills check-skills

test:
	./scripts/test.sh

health:
	./Web-UI/bin/media-stack-health

verify-binaries:
	./scripts/verify-binaries.sh

sync-skills:
	./scripts/sync-skills.sh --install

check-skills:
	./scripts/sync-skills.sh --check
