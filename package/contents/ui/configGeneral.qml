// SPDX-License-Identifier: MIT
import QtQuick
import QtQuick.Controls as QQC2
import QtQuick.Layouts
import org.kde.kirigami as Kirigami
import org.kde.kcmutils as KCM

KCM.SimpleKCM {
    property alias cfg_layerMode: layerMode.currentIndex
    property alias cfg_legendStyle: legendStyle.currentIndex
    property alias cfg_ghostTransparent: ghostTransparent.checked
    property alias cfg_keymapFile: keymapFile.text
    property int cfg_currentLayer

    // AppletConfiguration hands every page a *Default for every key
    property int cfg_layerModeDefault
    property int cfg_legendStyleDefault
    property bool cfg_ghostTransparentDefault
    property string cfg_keymapFileDefault
    property int cfg_currentLayerDefault

    Kirigami.FormLayout {
        QQC2.ComboBox {
            id: layerMode
            Kirigami.FormData.label: i18n("Layers:")
            model: [
                i18n("All, as tiles"),
                i18n("One at a time"),
                i18n("All, or one at a time when small"),
            ]
        }

        QQC2.ComboBox {
            id: legendStyle
            Kirigami.FormData.label: i18n("Legends:")
            model: [
                i18n("Symbols (⌫ ⇥ ⇧)"),
                i18n("Words (Bksp Tab Shift)"),
            ]
        }

        QQC2.CheckBox {
            id: ghostTransparent
            Kirigami.FormData.label: i18n("Transparent keys:")
            text: i18n("Show the base layer through them")
        }

        Item {
            Kirigami.FormData.isSection: true
        }

        QQC2.TextField {
            id: keymapFile
            Kirigami.FormData.label: i18n("Keymap file:")
            Layout.fillWidth: true
            placeholderText: "~/.local/share/plasma-zmk-keymap/keymap.json"
        }

        QQC2.Label {
            Layout.fillWidth: true
            Layout.maximumWidth: Kirigami.Units.gridUnit * 24
            wrapMode: Text.Wrap
            font: Kirigami.Theme.smallFont
            opacity: 0.7
            text: i18n("The widget reads your keymap over ZMK Studio's USB connection when you choose \"Read Keymap from Keyboard\" in its context menu, and keeps a copy in this file so it works with the keyboard unplugged.")
        }
    }
}
