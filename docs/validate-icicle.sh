#!/bin/bash

for i in `ls *.icicle`; do
    xmllint --noout --relaxng icicle.rng $i
done
