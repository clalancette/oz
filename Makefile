sdist:
	python setup.py sdist

rpm: sdist
	rpmbuild -ba oz.spec --define "_sourcedir `pwd`/dist"

srpm: sdist
	rpmbuild -bs oz.spec --define "_sourcedir `pwd`/dist"

validate:
	@echo "Validating TDL"
	@cd docs ; ./validate-tdl.sh
	@echo "Validating ICICLE"
	@cd docs ; ./validate-icicle.sh

clean:
	rm -rf MANIFEST build dist usr *~ oz.spec *.pyc oz/*~ oz/*.pyc examples/*~ oz/auto/*~ man/*~
