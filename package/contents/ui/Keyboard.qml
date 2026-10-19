// SPDX-License-Identifier: MIT
pragma ComponentBehavior: Bound

import QtQuick

import "keymap.js" as Keymap

// One layer drawn on the physical layout, sized to `unit` pixels per key.
Item {
    id: board

    property var layout
    property var layerKeys
    property var baseKeys
    property int layerIndex: -1
    property real unit
    property bool symbols: true
    property bool ghostTransparent: true

    signal layerClicked(int index)

    readonly property var bounds: Keymap.bounds(layout ? layout.keys : [])

    implicitWidth: bounds.w * unit
    implicitHeight: bounds.h * unit

    Repeater {
        model: board.layout ? board.layout.keys.length : 0

        Keycap {
            id: key

            required property int index
            readonly property var geo: board.layout.keys[index]
            readonly property real px: board.unit / 100

            x: (geo.x - board.bounds.x * 100) * px
            y: (geo.y - board.bounds.y * 100) * px
            width: geo.w * px
            height: geo.h * px
            transform: Rotation {
                origin.x: (key.geo.rx - key.geo.x) * key.px
                origin.y: (key.geo.ry - key.geo.y) * key.px
                angle: key.geo.r / 100
            }

            rotated: geo.r !== 0
            antialiasing: rotated
            unit: board.unit
            symbols: board.symbols
            binding: board.layerKeys ? board.layerKeys[index] : null
            fallback: board.ghostTransparent && board.baseKeys ? board.baseKeys[index] : null
            held: {
                const base = board.baseKeys ? board.baseKeys[index] : null;
                return !!base && base.layer === board.layerIndex && board.layerIndex > 0;
            }
            onLayerClicked: i => board.layerClicked(i)
        }
    }
}
