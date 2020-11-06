BIN=`which urlwatch`
CONFIG_DIR=config
URLS=${CONFIG_DIR}/urls.yaml
HOOKS=${CONFIG_DIR}/hooks.py
CACHE=${CONFIG_DIR}/cache.db
CONFIG=${CONFIG_DIR}/config.yaml

URLWATCH=urlwatch \
		--urls ${URLS} \
		--config ${CONFIG} \
		--hooks ${HOOKS} \
		--cache ${CACHE}

update:
	$(URLWATCH)

list:
	$(URLWATCH) --list

test:
	$(URLWATCH) --list | wc -l | xargs -n 1 -I {} $(URLWATCH) --test-filter {}

reset:
	rm $(CACHE)

install:
	pip3 install -Ur requirements.txt