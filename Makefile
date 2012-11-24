VERSION = $(shell egrep "^VERSION" setup.py | awk '{print $$3}')
VENV_DIR = tests/.venv

sdist:
	python setup.py sdist

signed-tarball: sdist
	gpg --detach-sign --armor -o dist/oz-$(VERSION).tar.gz.sign dist/oz-$(VERSION).tar.gz

signed-rpm: sdist
	rpmbuild -ba oz.spec --sign --define "_sourcedir `pwd`/dist"

rpm: sdist
	rpmbuild -ba oz.spec --define "_sourcedir `pwd`/dist"

srpm: sdist
	rpmbuild -bs oz.spec --define "_sourcedir `pwd`/dist"

deb:
	debuild -i -uc -us -b

release: signed-rpm signed-tarball deb

man2html:
	@for file in oz-install oz-customize oz-generate-icicle oz-cleanup-cache oz-examples; do \
		echo "Generating $$file HTML page from man" ; \
		groff -mandoc -mwww man/$$file.1 -T html > man/$$file.html ; \
	done

$(VENV_DIR):
	@virtualenv --system-site-packages $(VENV_DIR)
	@pip-python -E $(VENV_DIR) install pytest
	@[[ "$$PWD" =~ \ |\' ]] && ( \
	echo "Resolving potential problems where '$$PWD' contains spaces" ; \
	for MATCH in $$(grep '^#!"/' $(VENV_DIR)/bin/* -l) ; do \
		sed -i '1s|^#!".*/\([^/]*\)"|#!/usr/bin/env \1|' "$$MATCH" ; \
	done ) || true

virtualenv: $(VENV_DIR)

unittests:
	@[ -f $(VENV_DIR)/bin/activate ] && source $(VENV_DIR)/bin/activate ; python setup.py test
	@(type deactivate 2>/dev/null | grep -q 'function') && deactivate || true

pylint:
	pylint --rcfile=pylint.conf oz oz-install oz-customize oz-cleanup-cache oz-generate-icicle

clean:
	rm -rf MANIFEST build dist usr *~ oz.spec *.pyc oz/*~ oz/*.pyc examples/*~ oz/auto/*~ man/*~ docs/*~ man/*.html $(VENV_DIR) tests/tdl/*~ tests/factory/*~ tests/results.xml
