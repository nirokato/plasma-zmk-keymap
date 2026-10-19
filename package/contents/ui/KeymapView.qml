// SPDX-License-Identifier: MIT
pragma ComponentBehavior: Bound

import QtQuick
import org.kde.kirigami as Kirigami

import "keymap.js" as Keymap

// The whole cheatsheet. By default every layer is a tile, arranged in
// whichever grid (side by side, stacked, 2x2...) gives the biggest keys for
// the space, with a short last row centered. Alternatively one layer is shown
// with a tab strip. All sizes derive from a single key unit so the drawing
// scales as one piece.
Item {
    id: view

    property var keymap
    property int currentLayer: 0
    property int layerMode: 0 // 0 tiles, 1 one at a time, 2 tiles until too small
    property bool symbols: true
    property bool ghostTransparent: true

    readonly property var layers: keymap ? keymap.layers : []
    readonly property var layout: keymap ? keymap.layout : null
    readonly property var bounds: Keymap.bounds(layout ? layout.keys : [])
    readonly property int count: layers.length
    readonly property int shownLayer: Math.max(0, Math.min(currentLayer, count - 1))

    // chrome, in key units
    readonly property real tabsU: 0.75
    readonly property real labelU: 0.5
    readonly property real colGapU: 0.9
    readonly property real rowGapU: 0.35
    readonly property real minTileUnit: Kirigami.Units.gridUnit * 1.6

    readonly property real singleUnit: Math.min(width / bounds.w, height / (bounds.h + tabsU))

    // Best {columns, unit} for tiling every layer. Near-ties go to the grid
    // with fewer empty slots, so 4 layers prefer 2x2 over 3+1.
    readonly property var grid: {
        let best = null;
        for (let c = 1; c <= count; c++) {
            const r = Math.ceil(count / c);
            const u = Math.min(width / (c * bounds.w + (c - 1) * colGapU),
                               height / (r * (bounds.h + labelU) + (r - 1) * rowGapU));
            const empty = r * c - count;
            if (!best || u > best.unit * 1.03 || (u > best.unit * 0.97 && empty < best.empty)) {
                best = { columns: c, unit: u, empty: empty };
            }
        }
        return best || { columns: 1, unit: 0, empty: 0 };
    }

    readonly property bool tiled: count > 1 && (layerMode === 0
        || (layerMode === 2 && grid.unit >= minTileUnit))
    readonly property real unit: Math.max(3, Math.floor(tiled ? grid.unit : singleUnit))

    function step(delta) {
        if (count > 0) {
            currentLayer = (shownLayer + delta + count) % count;
        }
    }

    MouseArea {
        anchors.fill: parent
        acceptedButtons: Qt.NoButton
        enabled: !view.tiled && view.count > 1
        property real pending: 0
        onWheel: wheel => {
            pending += wheel.angleDelta.y || -wheel.angleDelta.x;
            while (Math.abs(pending) >= 120) {
                view.step(pending > 0 ? -1 : 1);
                pending -= Math.sign(pending) * 120;
            }
        }
    }

    Loader {
        anchors.centerIn: parent
        sourceComponent: view.tiled ? tiles : oneLayer
    }

    Component {
        id: oneLayer

        Column {
            LayerTabs {
                width: board.width
                height: view.tabsU * view.unit
                names: view.layers.map(l => l.name)
                current: view.shownLayer
                unit: view.unit
                onSelected: i => view.currentLayer = i
            }

            Keyboard {
                id: board
                layout: view.layout
                layerKeys: view.count ? view.layers[view.shownLayer].keys : null
                layerIndex: view.shownLayer
                baseKeys: view.shownLayer > 0 ? view.layers[0].keys : null
                unit: view.unit
                symbols: view.symbols
                ghostTransparent: view.ghostTransparent
                onLayerClicked: i => view.currentLayer = i
            }
        }
    }

    Component {
        id: tiles

        Item {
            id: grid

            readonly property int columns: view.grid.columns
            readonly property int rows: Math.ceil(view.count / columns)
            readonly property real tileW: view.bounds.w * view.unit
            readonly property real tileH: (view.bounds.h + view.labelU) * view.unit
            readonly property real gapX: view.colGapU * view.unit
            readonly property real gapY: view.rowGapU * view.unit

            implicitWidth: columns * tileW + (columns - 1) * gapX
            implicitHeight: rows * tileH + (rows - 1) * gapY

            Repeater {
                model: view.count

                Column {
                    id: tile

                    required property int index
                    readonly property int row: Math.floor(index / grid.columns)
                    readonly property int inRow: Math.min(grid.columns, view.count - row * grid.columns)
                    readonly property real indent: (grid.columns - inRow) * (grid.tileW + grid.gapX) / 2

                    x: indent + (index % grid.columns) * (grid.tileW + grid.gapX)
                    y: row * (grid.tileH + grid.gapY)
                    width: grid.tileW

                    Text {
                        readonly property real size: Math.max(7, view.unit * 0.22)

                        width: parent.width
                        height: view.labelU * view.unit
                        text: view.layers[tile.index].name
                        color: Kirigami.Theme.textColor
                        opacity: 0.55
                        font.family: Kirigami.Theme.defaultFont.family
                        font.pixelSize: size
                        font.weight: Font.Medium
                        font.letterSpacing: size * 0.06
                        font.capitalization: Font.AllUppercase
                        horizontalAlignment: Text.AlignHCenter
                        verticalAlignment: Text.AlignTop
                        elide: Text.ElideRight
                    }

                    Keyboard {
                        layout: view.layout
                        layerKeys: view.layers[tile.index].keys
                        layerIndex: tile.index
                        baseKeys: tile.index > 0 ? view.layers[0].keys : null
                        unit: view.unit
                        symbols: view.symbols
                        ghostTransparent: view.ghostTransparent
                    }
                }
            }
        }
    }
}
