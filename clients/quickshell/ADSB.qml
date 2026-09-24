pragma Singleton
import QtQuick
import Quickshell.Io

Item {
    id: root

    property string apiUrl: "https://overheadadsb.mydomain.tld/api/v1/overhead"
    property int refreshIntervalMs: 5000
    property string idleText: ""

    readonly property string planeIcon: "\uf072"
    readonly property string heliIcon: "\uedfd"

    property var lastData: null
    property bool hasError: false

    readonly property string displayText: {
        if (!root.lastData) return root.idleText

        var d = root.lastData
        var parts = []

        if (d.squawk_meaning) parts.push(d.squawk_meaning)

        var icon = iconFor(d.category)
        if (icon.length > 0) parts.push(icon)

        parts.push(d.owner || d.registration || d.icao)

        return parts.join(" ")
    }

    function iconFor(category) {
        if (category === "PLANE") return root.planeIcon
        if (category === "HELI") return root.heliIcon
        return ""
    }

    Process {
        id: fetcher
        command: ["curl", "-s", "--max-time", "3", root.apiUrl]
        running: true

        stdout: StdioCollector {
            onStreamFinished: {
                try {
                    var parsed = JSON.parse(this.text)
                    root.lastData = parsed.data
                    root.hasError = false
                } catch (e) {
                    console.warn("AircraftTracker: failed to parse response —", e)
                    root.hasError = true
                }
            }
        }
    }

    Timer {
        interval: root.refreshIntervalMs
        running: true
        repeat: true
        onTriggered: fetcher.running = true
    }
}
