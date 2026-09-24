import Quickshell
Scope {
  Variants {
    model: Quickshell.screens
    PanelWindow {
      required property var modelData
      screen: modelData
      anchors { top: true; left: true; right: true }
      implicitHeight: 30

      ABSBWidget {
        anchors.right: parent.right
        anchors.rightMargin: 8
        anchors.verticalCenter: parent.verticalCenter
        displayText: ADSB.displayText
        hasError: ABSD.hasError
      }
    }
  }
}
