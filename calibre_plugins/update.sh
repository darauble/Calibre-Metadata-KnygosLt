#!/bin/bash
############################################################
# Updates plugin in the Calibre's plugin directory (must be installed first) and runs included test(s)
# in the shell for quick development review.
############################################################

PLUGIN=knygoslt
killall calibre
killall calibre-debug
cd $PLUGIN
zip $PLUGIN.zip `find . -type f`
mv "$PLUGIN.zip" ~/.config/calibre/plugins/Knygos.lt.zip
#calibre-debug -g
calibre-debug -e __init__.py
cat /tmp/Knygos.lt_identify_test.txt

