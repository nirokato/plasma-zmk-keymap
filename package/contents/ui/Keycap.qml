// SPDX-License-Identifier: MIT
import QtQuick
import QtQuick.Controls as QQC2
import org.kde.kirigami as Kirigami

import "keymap.js" as Keymap

Item {
    id: cap

    property var binding
    property var fallback // what a transparent key falls through to
    property bool held // this key holds the layer being shown
    property bool rotated // native glyph rendering looks jagged at an angle
    property real unit
    property bool symbols: true

    signal layerClicked(int index)

    readonly property string kind: binding ? binding.kind : "none"
    readonly property var legend: Keymap.legend(binding, symbols)
    readonly property var ghost: kind === "trans" ? Keymap.legend(fallback, symbols) : null
    readonly property string tapText: ghost ? ghost.tap : legend.tap
    readonly property string holdText: ghost ? ghost.hold : legend.hold
    readonly property bool isLayer: kind === "layer" || (kind === "holdtap" && binding.layer !== undefined)
    readonly property bool glyph: tapText.length <= 2

    readonly property color ink: Kirigami.Theme.textColor
    readonly property color accent: Kirigami.Theme.highlightColor

    function tint(c, a) {
        return Qt.rgba(c.r, c.g, c.b, a);
    }

    Rectangle {
        id: face
        anchors.fill: parent
        anchors.margins: Math.max(1, cap.unit * 0.035)
        radius: cap.unit * 0.12
        color: cap.held ? cap.tint(cap.accent, 0.32)
             : cap.kind === "trans" || cap.kind === "none" ? cap.tint(cap.ink, 0.03)
             : hover.hovered && cap.isLayer ? cap.tint(cap.accent, 0.22)
             : cap.isLayer ? cap.tint(cap.accent, 0.13)
             : cap.tint(cap.ink, 0.075)
        border.width: 1
        border.color: cap.held ? cap.tint(cap.accent, 0.5)
                    : cap.kind === "trans" || cap.kind === "none" ? "transparent"
                    : cap.tint(cap.ink, 0.06)

        Behavior on color {
            ColorAnimation { duration: Kirigami.Units.shortDuration }
        }

        Text {
            id: tap
            anchors {
                left: parent.left
                right: parent.right
                verticalCenter: parent.verticalCenter
                verticalCenterOffset: cap.holdText ? -cap.unit * 0.1 : 0
                leftMargin: cap.unit * 0.07
                rightMargin: cap.unit * 0.07
            }
            height: parent.height * (cap.holdText ? 0.5 : 0.8)
            text: cap.tapText
            renderType: cap.rotated ? Text.QtRendering : Text.NativeRendering
            color: cap.isLayer || cap.held ? cap.accent : cap.ink
            opacity: cap.ghost && !cap.held ? 0.3 : 1
            font.family: Kirigami.Theme.defaultFont.family
            font.pixelSize: Math.max(6, cap.unit * (cap.glyph ? 0.34 : 0.23))
            font.weight: cap.glyph ? Font.Normal : Font.Medium
            fontSizeMode: Text.Fit
            // shrink rather than elide; at tile sizes an ellipsis reads as noise
            minimumPixelSize: Math.min(4, cap.unit * 0.13)
            horizontalAlignment: Text.AlignHCenter
            verticalAlignment: Text.AlignVCenter
            wrapMode: Text.WordWrap
            maximumLineCount: 2
        }

        Text {
            anchors {
                left: parent.left
                right: parent.right
                bottom: parent.bottom
                bottomMargin: cap.unit * 0.08
                leftMargin: cap.unit * 0.06
                rightMargin: cap.unit * 0.06
            }
            visible: cap.holdText !== ""
            text: cap.holdText
            renderType: cap.rotated ? Text.QtRendering : Text.NativeRendering
            color: cap.isLayer && cap.kind === "holdtap" ? cap.accent : cap.ink
            opacity: cap.ghost ? 0.2 : 0.55
            font.family: Kirigami.Theme.defaultFont.family
            font.pixelSize: Math.max(4, cap.unit * 0.16)
            fontSizeMode: Text.HorizontalFit
            minimumPixelSize: 4
            horizontalAlignment: Text.AlignHCenter
        }
    }

    HoverHandler {
        id: hover
        cursorShape: cap.isLayer ? Qt.PointingHandCursor : Qt.ArrowCursor
    }

    TapHandler {
        enabled: cap.isLayer
        onTapped: cap.layerClicked(cap.binding.layer)
    }

    QQC2.ToolTip.visible: hover.hovered && cap.kind !== "none"
    QQC2.ToolTip.delay: Kirigami.Units.toolTipDelay
    QQC2.ToolTip.text: Keymap.describe(cap.binding)
}
