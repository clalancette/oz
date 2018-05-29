VERSION = $(shell egrep "^VERSION" setup.py | awk '{print $$3}')
VENV_DIR = tests/.venv

sdist: oz.spec.in
	python setup.py sdist

oz.spec: sdist

signed-tarball: sdist
	gpg --detach-sign --armor -o dist/oz-$(VERSION).tar.gz.sign dist/oz-$(VERSION).tar.gz

signed-rpm: oz.spec
	rpmbuild -ba oz.spec --sign --define "_sourcedir `pwd`/dist"

rpm: oz.spec
	rpmbuild -ba oz.spec --define "_sourcedir `pwd`/dist"

srpm: oz.spec
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

tests: unittests

test-coverage:
	python-coverage run --source oz /usr/bin/py.test --verbose tests
	python-coverage html
	xdg-open htmlcov/index.html

pylint:
	pylint --rcfile=pylint.conf oz oz-install oz-customize oz-cleanup-cache oz-generate-icicle

clean:
	rm -rf MANIFEST build dist usr *~ oz.spec *.pyc oz/*~ oz/*.pyc examples/*~ oz/auto/*~ man/*~ docs/*~ man/*.html $(VENV_DIR) tests/tdl/*~ tests/factory/*~ tests/results.xml htmlcov

.PHONY: sdist oz.spec signed-tarball signed-rpm rpm srpm deb release man2html virtualenv unittests tests test-coverage pylint clean
