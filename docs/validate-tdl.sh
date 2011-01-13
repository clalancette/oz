#!/bin/bash

for i in `ls *.tdl`; do
    xmllint --noout --relaxng tdl.rng $i
done
