import QtQuick

Text {
    required property string displayText
    required property bool hasError

    text: displayText
    color: hasError ? "#f38ba8" : "#cdd6f4"
    font.family: "Iosevka Nerd Font Mono"
    font.pixelSize: 13
}
