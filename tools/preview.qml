// Offscreen render of KeymapView at a few widget sizes; see tools/preview.sh.
import QtQuick
import QtQuick.Window
import org.kde.kirigami as Kirigami

import "../package/contents/ui"

Window {
    id: win

    readonly property var args: {
        const a = Qt.application.arguments;
        return a.slice(a.indexOf("--") + 1);
    }
    readonly property string docPath: args[0]
    readonly property string outDir: args[1]
    readonly property var sizes: JSON.parse(args[2])
    property int index: 0
    property var doc

    width: 1600
    height: 1000
    visible: true
    color: "#2a2e32"

    // Breeze roles; dark is also what a background-less widget gets on the desktop
    readonly property bool dark: !!sizes[index].dark
    readonly property bool bare: !!sizes[index].bare

    Rectangle {
        id: plate
        width: win.sizes[win.index].w
        height: win.sizes[win.index].h
        radius: Kirigami.Units.cornerRadius
        gradient: win.bare ? wallpaper : null
        color: Kirigami.Theme.backgroundColor

        Kirigami.Theme.inherit: false
        Kirigami.Theme.textColor: win.sizes[win.index].ink || (win.dark ? "#fcfcfc" : "#232629")
        Kirigami.Theme.backgroundColor: win.sizes[win.index].paper || (win.dark ? "#202326" : "#eff0f1")
        Kirigami.Theme.highlightColor: win.sizes[win.index].accent || "#3daee9"

        Gradient {
            id: wallpaper
            orientation: Gradient.Horizontal
            GradientStop { position: 0; color: "#1d2b3a" }
            GradientStop { position: 0.6; color: "#3b3550" }
            GradientStop { position: 1; color: "#5a4136" }
        }

        KeymapView {
            anchors.fill: parent
            anchors.margins: Kirigami.Units.largeSpacing
            keymap: win.doc
            currentLayer: win.sizes[win.index].layer || 0
            layerMode: win.sizes[win.index].mode || 0
            symbols: win.sizes[win.index].text ? false : true
        }
    }

    Timer {
        id: tick
        interval: 400
        onTriggered: plate.grabToImage(result => {
            const s = win.sizes[win.index];
            result.saveToFile(win.outDir + "/" + s.name + ".png");
            if (win.index + 1 < win.sizes.length) {
                win.index++;
                tick.start();
            } else {
                Qt.quit();
            }
        })
    }

    Component.onCompleted: {
        const xhr = new XMLHttpRequest();
        xhr.open("GET", "file://" + docPath, false);
        xhr.send();
        doc = JSON.parse(xhr.responseText);
        tick.start();
    }
}
