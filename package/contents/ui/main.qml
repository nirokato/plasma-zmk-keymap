// SPDX-License-Identifier: MIT
import QtQuick
import QtQuick.Layouts
import org.kde.kirigami as Kirigami
import org.kde.plasma.core as PlasmaCore
import org.kde.plasma.extras as PlasmaExtras
import org.kde.plasma.plasma5support as P5Support
import org.kde.plasma.plasmoid

PlasmoidItem {
    id: root

    property var keymap: null
    // loading | ready | empty | reading | unlock | error
    property string phase: "loading"
    property string message: ""
    property var pending: ({})

    readonly property bool planar: Plasmoid.formFactor === PlasmaCore.Types.Planar
    readonly property bool reading: phase === "reading" || phase === "unlock"
    readonly property string helper: decodeURIComponent(
        Qt.resolvedUrl("../code/zmkkeymap.py").toString().replace(/^file:\/\//, ""))

    // initial size on the desktop; room for three Corne layers as 2+1 tiles
    width: Kirigami.Units.gridUnit * 44
    height: Kirigami.Units.gridUnit * 20

    Plasmoid.icon: "input-keyboard"
    Plasmoid.backgroundHints: PlasmaCore.Types.DefaultBackground | PlasmaCore.Types.ConfigurableBackground
    preferredRepresentation: planar ? fullRepresentation : null
    switchWidth: planar ? -1 : Kirigami.Units.gridUnit * 14
    switchHeight: planar ? -1 : Kirigami.Units.gridUnit * 6

    toolTipMainText: keymap ? keymap.device.name : i18n("ZMK Keymap")
    toolTipSubText: keymap ? i18np("%1 layer", "%1 layers", keymap.layers.length) : ""

    Plasmoid.contextualActions: [
        PlasmaCore.Action {
            text: i18n("Read Keymap from Keyboard")
            icon.name: "view-refresh"
            enabled: !root.reading
            onTriggered: root.fetch()
        }
    ]

    function quote(s) {
        return "'" + s.replace(/'/g, "'\\''") + "'";
    }

    function command(args) {
        const file = Plasmoid.configuration.keymapFile;
        const port = Plasmoid.configuration.serialPort;
        return ["python3", "-I", quote(helper)]
            .concat(file ? ["--out", quote(file)] : [], port ? ["--port", quote(port)] : [], args)
            .join(" ");
    }

    function run(op, args) {
        const cmd = command(args);
        pending[cmd] = op;
        exec.connectSource(cmd);
    }

    function load() {
        run("show", ["show"]);
    }

    // probe first so we can ask for an unlock before the fetch blocks on it
    function fetch() {
        phase = "reading";
        message = "";
        run("probe", ["probe"]);
    }

    function handle(op, stdout, stderr) {
        let doc;
        try {
            doc = JSON.parse(stdout);
        } catch (e) {
            fail(stderr.trim() || i18n("The keymap helper did not run. Is python3 installed?"));
            return;
        }
        if (doc.error === "no-cache") {
            phase = keymap ? "ready" : "empty";
        } else if (doc.error) {
            fail(doc.message);
        } else if (op === "probe") {
            phase = doc.unlocked ? "reading" : "unlock";
            run("fetch", ["fetch", "--wait", "120"]);
        } else {
            keymap = doc;
            phase = "ready";
        }
    }

    function fail(text) {
        message = text;
        phase = keymap ? "ready" : "error";
    }

    P5Support.DataSource {
        id: exec
        engine: "executable"
        connectedSources: []
        onNewData: (source, data) => {
            disconnectSource(source);
            const op = root.pending[source];
            delete root.pending[source];
            root.handle(op, data["stdout"], data["stderr"]);
        }
    }

    Connections {
        target: Plasmoid.configuration
        function onKeymapFileChanged() {
            root.load();
        }
    }

    Component.onCompleted: load()

    fullRepresentation: Item {
        Layout.minimumWidth: Kirigami.Units.gridUnit * 12
        Layout.minimumHeight: Kirigami.Units.gridUnit * 5
        Layout.preferredWidth: Kirigami.Units.gridUnit * 44
        Layout.preferredHeight: Kirigami.Units.gridUnit * 20

        KeymapView {
            anchors.fill: parent
            visible: !!root.keymap
            keymap: root.keymap
            currentLayer: Plasmoid.configuration.currentLayer
            layerMode: Plasmoid.configuration.layerMode
            symbols: Plasmoid.configuration.legendStyle === 0
            ghostTransparent: Plasmoid.configuration.ghostTransparent
            onCurrentLayerChanged: Plasmoid.configuration.currentLayer = currentLayer
        }

        PlasmaExtras.PlaceholderMessage {
            anchors.centerIn: parent
            width: parent.width - Kirigami.Units.gridUnit * 2
            visible: !root.keymap && root.phase !== "loading"
            iconName: root.phase === "error" ? "dialog-warning" : "input-keyboard"
            text: root.phase === "unlock" ? i18n("Unlock your keyboard")
                : root.phase === "reading" ? i18n("Reading keymap…")
                : root.phase === "error" ? i18n("Couldn't read the keymap")
                : i18n("No keymap yet")
            explanation: root.phase === "unlock" ? i18n("Press the key bound to %1.", "&studio_unlock")
                : root.phase === "error" ? root.message
                : root.phase === "empty" ? i18n("Plug your ZMK keyboard in over USB, with ZMK Studio enabled.")
                : ""
            helpfulAction: root.reading ? null : readAction

            Kirigami.Action {
                id: readAction
                text: i18n("Read from Keyboard")
                icon.name: "view-refresh"
                onTriggered: root.fetch()
            }
        }

        // status for a refresh while a keymap is already on screen
        Kirigami.InlineMessage {
            anchors {
                left: parent.left
                right: parent.right
                bottom: parent.bottom
            }
            visible: !!root.keymap && (root.reading || root.message !== "")
            type: root.message ? Kirigami.MessageType.Warning : Kirigami.MessageType.Information
            text: root.phase === "unlock" ? i18n("Press the key bound to %1 to read the keymap.", "&studio_unlock")
                : root.reading ? i18n("Reading keymap…")
                : root.message
            actions: Kirigami.Action {
                text: i18n("Dismiss")
                icon.name: "dialog-close"
                displayHint: Kirigami.DisplayHint.IconOnly
                visible: !root.reading
                onTriggered: root.message = ""
            }
        }
    }
}
