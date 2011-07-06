#!/bin/bash

export PYTHONPATH=../..:$PYTHONPATH

if [ -z "$DEBUG" ]; then
    DEBUG=0
fi

SUCCESS=0
FAIL=0

success() {
    echo "OK"
    SUCCESS=$(( $SUCCESS + 1 ))
}

failure() {
    echo "FAIL"
    FAIL=$(( $FAIL + 1 ))
}

schema_test() {
    schema="$1"
    expectsuccess="$2"

    echo -n "Testing Schema $schema..."

    if [ ! -r "$1" ]; then
	echo "FAIL: File not found"
	FAIL=$(( $FAIL + 1 ))
	return
    fi
    if [ $DEBUG -eq 0 ]; then
	xmllint --noout --relaxng ../../docs/tdl.rng "$schema" >& /dev/null
    else
	xmllint --relaxng ../../docs/tdl.rng "$schema"
    fi

    RET=$?

    if [ $RET -eq 0 -a "$expectsuccess" = "true" ] || [ $RET -ne 0 -a "$expectsuccess" != "true" ]; then
	success
    else
	failure
    fi
}

python_test() {
    parse="$1"
    expectsuccess="$2"

    echo -n "Testing Parsing $1..."
    if [ ! -r "$1" ]; then
	echo "FAIL: File not found"
	FAIL=$(( $FAIL + 1 ))
	return
    fi

    if [ $DEBUG -eq 0 ]; then
	python test_tdl.py "$1" >& /dev/null
    else
	python test_tdl.py "$1"
    fi

    RET=$?

    if [ $RET -eq 0 -a "$expectsuccess" = "true" ] || [ $RET -ne 0 -a "$expectsuccess" != "true" ]; then
	success
    else
	failure
    fi
}

expect_success() {
    schema_test "$1" "true"
    python_test "$1" "true"
}

expect_fail() {
    schema_test "$1" "false"
    python_test "$1" "false"
}

expect_success test-01-simple-iso.tdl
expect_success test-02-simple-url.tdl
expect_fail test-03-empty-template.tdl
expect_fail test-04-no-os.tdl
expect_fail test-05-no-name.tdl
expect_success test-06-simple-iso-description.tdl
expect_success test-07-packages-no-package.tdl
expect_success test-08-repositories-no-repository.tdl
expect_fail test-09-os-invalid-arch.tdl
expect_fail test-10-os-invalid-install-type.tdl
expect_success test-11-description-packages-repositories.tdl
expect_fail test-12-os-no-name.tdl
expect_fail test-13-os-no-version.tdl
expect_fail test-14-os-no-arch.tdl
expect_fail test-15-os-no-install.tdl
expect_success test-16-signed-repository.tdl
expect_fail test-17-repo-invalid-signed.tdl
expect_success test-18-rootpw.tdl
expect_success test-19-key.tdl
expect_fail test-20-multiple-install.tdl
expect_fail test-21-missing-install-type.tdl
expect_success test-22-md5sum.tdl
expect_success test-23-sha1sum.tdl
expect_success test-24-sha256sum.tdl
expect_fail test-25-md5sum-and-sha1sum.tdl
expect_fail test-26-md5sum-and-sha256sum.tdl
expect_fail test-27-sha1sum-and-sha256sum.tdl

echo "SUCCESS: $SUCCESS, FAIL: $FAIL"
exit $FAIL
