ID := com.nirokato.zmkkeymap

.PHONY: install upgrade uninstall test preview lint

install:
	kpackagetool6 -t Plasma/Applet -i package

upgrade:
	kpackagetool6 -t Plasma/Applet -u package

uninstall:
	kpackagetool6 -t Plasma/Applet -r $(ID)

test:
	python3 -m unittest discover -s tests

preview:
	tools/preview.sh

lint:
	/usr/lib/qt6/bin/qmllint -I /usr/lib/qt6/qml package/contents/ui/*.qml
