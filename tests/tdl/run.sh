#!/bin/bash

export PYTHONPATH=../..:$PYTHONPATH

if [ -z "$DEBUG" ]; then
    DEBUG=0
fi

schema_expect_success() {
    echo -n "Testing Schema $1..."
    if [ ! -r "$1" ]; then
	echo "File not found"
	return
    fi
    if [ $DEBUG -eq 0 ]; then
	xmllint --noout --relaxng ../../docs/tdl.rng "$1" >& /dev/null
    else
	xmllint --relaxng ../../docs/tdl.rng "$1"
    fi
    if [ $? -eq 0 ]; then
	echo "OK"
    else
	echo "FAIL"
    fi
}
schema_expect_fail() {
    echo -n "Testing Schema $1..."
    if [ ! -r "$1" ]; then
	echo "File not found"
	return
    fi
    if [ $DEBUG -eq 0 ]; then
	xmllint --noout --relaxng ../../docs/tdl.rng "$1" >& /dev/null
    else
	xmllint --relaxng ../../docs/tdl.rng "$1"
    fi
    if [ $? -ne 0 ]; then
	echo "OK"
    else
	echo "FAIL"
    fi
}

python_expect_success() {
    echo -n "Testing Parsing $1..."
    if [ ! -r "$1" ]; then
	echo "File not found"
	return
    fi

    if [ $DEBUG -eq 0 ]; then
	python test_tdl.py "$1" >& /dev/null
    else
	python test_tdl.py "$1"
    fi

    if [ $? -eq 0 ]; then
	echo "OK"
    else
	echo "FAIL"
    fi
}
python_expect_fail() {
    echo -n "Testing Parsing $1..."
    if [ ! -r "$1" ]; then
	echo "File not found"
	return
    fi

    if [ $DEBUG -eq 0 ]; then
	python test_tdl.py "$1" >& /dev/null
    else
	python test_tdl.py "$1"
    fi

    if [ $? -ne 0 ]; then
	echo "OK"
    else
	echo "FAIL"
    fi
}

schema_expect_success test-01-simple-iso.tdl
schema_expect_success test-02-simple-url.tdl
schema_expect_fail test-03-empty-template.tdl
schema_expect_fail test-04-no-os.tdl
schema_expect_fail test-05-no-name.tdl
schema_expect_success test-06-simple-iso-description.tdl
schema_expect_success test-07-packages-no-package.tdl
schema_expect_success test-08-repositories-no-repository.tdl
schema_expect_fail test-09-os-invalid-arch.tdl
schema_expect_fail test-10-os-invalid-install-type.tdl
schema_expect_success test-11-description-packages-repositories.tdl
schema_expect_fail test-12-os-no-name.tdl
schema_expect_fail test-13-os-no-version.tdl
schema_expect_fail test-14-os-no-arch.tdl
schema_expect_fail test-15-os-no-install.tdl
schema_expect_success test-16-signed-repository.tdl
schema_expect_fail test-17-repo-invalid-signed.tdl

python_expect_success test-01-simple-iso.tdl
python_expect_success test-02-simple-url.tdl
python_expect_fail test-03-empty-template.tdl
python_expect_fail test-04-no-os.tdl
python_expect_fail test-05-no-name.tdl
python_expect_success test-06-simple-iso-description.tdl
python_expect_success test-07-packages-no-package.tdl
python_expect_success test-08-repositories-no-repository.tdl
python_expect_fail test-09-os-invalid-arch.tdl
python_expect_fail test-10-os-invalid-install-type.tdl
python_expect_success test-11-description-packages-repositories.tdl
python_expect_fail test-12-os-no-name.tdl
python_expect_fail test-13-os-no-version.tdl
python_expect_fail test-14-os-no-arch.tdl
python_expect_fail test-15-os-no-install.tdl
python_expect_success test-16-signed-repository.tdl
python_expect_fail test-17-repo-invalid-signed.tdl
