sdist:
	python setup.py sdist

signed-rpm: sdist
	rpmbuild -ba oz.spec --sign --define "_sourcedir `pwd`/dist"

rpm: sdist
	rpmbuild -ba oz.spec --define "_sourcedir `pwd`/dist"

srpm: sdist
	rpmbuild -bs oz.spec --define "_sourcedir `pwd`/dist"

man2html:
	@echo "Generating oz-install HTML page from man"
	@groff -mandoc man/oz-install.1 -T html > man/oz-install.html
	@echo "Generating oz-customize HTML page from man"
	@groff -mandoc man/oz-customize.1 -T html > man/oz-customize.html
	@echo "Generating oz-generate-icicle HTML page from man"
	@groff -mandoc man/oz-generate-icicle.1 -T html > man/oz-generate-icicle.html
	@echo "Generating oz-cleanup-cache HTML page from man"
	@groff -mandoc man/oz-cleanup-cache.1 -T html > man/oz-cleanup-cache.html

unittests:
	@cd tests/tdl ; ./run.sh
	@cd tests/factory ; ./run.sh

pylint:
	pylint --rcfile=pylint.conf oz

clean:
	rm -rf MANIFEST build dist usr *~ oz.spec *.pyc oz/*~ oz/*.pyc examples/*~ oz/auto/*~ man/*~ docs/*~ man/*.html tests/tdl/*~ tests/factory/*~
