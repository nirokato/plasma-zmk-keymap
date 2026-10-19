// SPDX-License-Identifier: MIT
pragma ComponentBehavior: Bound

import QtQuick
import org.kde.kirigami as Kirigami

// Layer names as quiet tabs; the active one gets full ink and an underline
// that slides between tabs.
Item {
    id: tabs

    property var names: []
    property int current: 0
    property real unit

    signal selected(int index)

    readonly property real fontSize: Math.max(8, unit * 0.22)

    Item {
        id: strip
        anchors.horizontalCenter: parent.horizontalCenter
        anchors.top: parent.top
        width: row.implicitWidth
        height: parent.height - tabs.unit * 0.18
        scale: Math.min(1, tabs.width / Math.max(1, width))

        Row {
            id: row
            height: parent.height
            spacing: tabs.unit * 0.4

            Repeater {
                id: repeater
                model: tabs.names

                Text {
                    id: tab

                    required property int index
                    required property string modelData

                    height: row.height
                    text: tab.modelData
                    color: Kirigami.Theme.textColor
                    opacity: tab.index === tabs.current ? 1 : hover.hovered ? 0.75 : 0.45
                    font.family: Kirigami.Theme.defaultFont.family
                    font.pixelSize: tabs.fontSize
                    font.weight: Font.Medium
                    font.letterSpacing: tabs.fontSize * 0.06
                    font.capitalization: Font.AllUppercase
                    verticalAlignment: Text.AlignVCenter

                    Behavior on opacity {
                        NumberAnimation { duration: Kirigami.Units.shortDuration }
                    }

                    HoverHandler {
                        id: hover
                        cursorShape: Qt.PointingHandCursor
                    }

                    TapHandler {
                        onTapped: tabs.selected(tab.index)
                    }
                }
            }
        }

        Rectangle {
            // itemAt() doesn't notify; reading count re-evaluates once delegates exist
            readonly property Item target: repeater.count > tabs.current ? repeater.itemAt(tabs.current) : null

            y: strip.height - height
            x: target ? target.x : 0
            width: target ? target.width : 0
            height: Math.max(2, Math.round(tabs.unit * 0.04))
            radius: height / 2
            color: Kirigami.Theme.highlightColor

            Behavior on x {
                NumberAnimation { duration: Kirigami.Units.longDuration; easing.type: Easing.OutCubic }
            }
            Behavior on width {
                NumberAnimation { duration: Kirigami.Units.longDuration; easing.type: Easing.OutCubic }
            }
        }
    }
}
