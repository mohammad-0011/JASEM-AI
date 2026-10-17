import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtQuick.Effects

ApplicationWindow {
    id: win
    width: 1320
    height: 860
    minimumWidth: 1040
    minimumHeight: 700
    visible: true
    title: "جاسم — دستیار صوتی"
    color: "#04070f"

    // Right-to-left for Persian content
    LayoutMirroring.enabled: true
    LayoutMirroring.childrenInherit: true

    property color accent: "#22d3ee"
    property color accent2: "#3b82f6"
    property color bg1: "#04070f"
    property color bg2: "#0a1224"
    property color panel: "#0b1428"
    property color panelBorder: "#16304f"
    property color textMain: "#d9ecff"
    property color textDim: "#7f98b8"

    property real micLvl: 0
    property real playLvl: 0
    property string currentState: "idle"
    property bool confirmationOpen: false
    property string confirmationText: ""

    readonly property var stateLabels: ({
        "idle": "آماده",
        "wake_monitoring": "در حال گوش دادن…",
        "listening": "دارم گوش می‌دم…",
        "processing": "دارم می‌شنومت…",
        "generating": "دارم فکر می‌کنم…",
        "speaking": "دارم جواب می‌دم…",
        "confirming": "منتظر تأیید توام…",
        "interrupted": "قطع شد",
        "error": "خطا",
        "shutdown": "خاموش"
    })
    readonly property var stateColors: ({
        "idle": "#7f98b8", "wake_monitoring": "#22d3ee", "listening": "#22d3ee",
        "processing": "#f59e0b", "generating": "#a78bfa", "speaking": "#a78bfa",
        "confirming": "#f59e0b", "interrupted": "#f97316", "error": "#ef4444",
        "shutdown": "#64748b"
    })
    property color stateColor: stateColors[currentState] || accent

    font.family: "Vazirmatn, Segoe UI, Tahoma"
    font.pixelSize: 14

    ListModel { id: messages }

    Connections {
        target: bridge
        function onMicLevel(v) { win.micLvl = v }
        function onPlayLevel(v) { win.playLvl = v }
        function onStateChanged(n, o, r) { win.currentState = n }
        function onMessageAdded(role, text, ts) {
            messages.append({role: role, text: text, ts: ts})
            if (messages.count > 300) messages.remove(0)
            listView.positionViewAtEnd()
        }
        function onConfirmationRequested(text) {
            win.confirmationText = text
            win.confirmationOpen = true
        }
        function onConfirmationVisible(v) { if (!v) win.confirmationOpen = false }
        function onNotification(text) { toast.show(text) }
        function onWakeDetected(phrase) { corePulse.flash() }
        function onStatusChanged(service, ok, detail) {
            statusModel.setStatus(service, ok, detail)
        }
    }

    // ================= background =================
    Rectangle {
        anchors.fill: parent
        z: -1
        gradient: Gradient {
            GradientStop { position: 0.0; color: win.bg2 }
            GradientStop { position: 0.55; color: win.bg1 }
            GradientStop { position: 1.0; color: "#020409" }
        }
    }
    Canvas {
        id: gridBg
        anchors.fill: parent
        z: -1
        opacity: 0.10
        onPaint: {
            const ctx = getContext("2d")
            ctx.clearRect(0, 0, width, height)
            ctx.strokeStyle = "#1e5f8a"
            ctx.lineWidth = 1
            for (let x = 0; x < width; x += 48) { ctx.beginPath(); ctx.moveTo(x, 0); ctx.lineTo(x, height); ctx.stroke() }
            for (let y = 0; y < height; y += 48) { ctx.beginPath(); ctx.moveTo(0, y); ctx.lineTo(width, y); ctx.stroke() }
        }
    }

    // ================= layout =================
    ColumnLayout {
        anchors.fill: parent
        anchors.margins: 18
        spacing: 14

        // -------- header --------
        Rectangle {
            Layout.fillWidth: true
            Layout.preferredHeight: 64
            radius: 14
            color: Qt.rgba(0.043, 0.078, 0.157, 0.72)
            border.color: win.panelBorder
            border.width: 1

            RowLayout {
                anchors.fill: parent
                anchors.leftMargin: 18
                anchors.rightMargin: 18
                spacing: 14

                // logo + name
                Rectangle {
                    width: 36; height: 36; radius: 18
                    gradient: Gradient {
                        GradientStop { position: 0; color: win.accent }
                        GradientStop { position: 1; color: win.accent2 }
                    }
                    Rectangle { anchors.centerIn: parent; width: 14; height: 14; radius: 7; color: "#04070f" }
                }
                Column {
                    spacing: 1
                    Text { text: "جاسم"; color: win.textMain; font.pixelSize: 20; font.bold: true }
                    Text { text: "JASEM · Persian Voice Assistant"; color: win.textDim; font.pixelSize: 10; font.letterSpacing: 1 }
                }

                Item { Layout.fillWidth: true }

                // live state pill
                Rectangle {
                    Layout.preferredHeight: 34
                    Layout.preferredWidth: statePillRow.implicitWidth + 32
                    radius: 17
                    color: Qt.rgba(0, 0, 0, 0.35)
                    border.color: win.stateColor
                    border.width: 1.5
                    RowLayout {
                        id: statePillRow
                        anchors.centerIn: parent
                        spacing: 8
                        Rectangle {
                            width: 9; height: 9; radius: 5
                            color: win.stateColor
                            SequentialAnimation on opacity {
                                loops: Animation.Infinite
                                running: win.currentState === "listening" || win.currentState === "speaking" || win.currentState === "wake_monitoring"
                                NumberAnimation { to: 0.25; duration: 600 }
                                NumberAnimation { to: 1.0; duration: 600 }
                            }
                        }
                        Text {
                            text: win.stateLabels[win.currentState] || win.currentState
                            color: win.stateColor; font.pixelSize: 14; font.bold: true
                        }
                    }
                }

                // status pills
                Repeater {
                    model: ListModel { id: statusModel
                        property var map: ({})
                        function setStatus(service, ok, detail) {
                            map[service] = {ok: ok, detail: detail}
                            var found = false
                            for (var i = 0; i < count; i++) {
                                if (get(i).service === service) {
                                    setProperty(i, "ok", ok); setProperty(i, "detail", detail); found = true; break
                                }
                            }
                            if (!found) append({service: service, ok: ok, detail: detail})
                        }
                        Component.onCompleted: {
                            append({service: "mic", ok: true, detail: "میکروفن"})
                            append({service: "stt", ok: false, detail: "شنیدن"})
                            append({service: "tts", ok: false, detail: "صداسازی"})
                            append({service: "ai", ok: false, detail: "هوش"})
                        }
                    }
                    delegate: Rectangle {
                        required property string service
                        required property bool ok
                        required property string detail
                        Layout.preferredHeight: 30
                        Layout.preferredWidth: pillRow.implicitWidth + 24
                        radius: 15
                        color: Qt.rgba(0, 0, 0, 0.35)
                        border.color: ok ? "#14b8a6" : "#ef4444"
                        border.width: 1
                        RowLayout {
                            id: pillRow
                            anchors.centerIn: parent
                            spacing: 6
                            Rectangle { width: 7; height: 7; radius: 4; color: ok ? "#2dd4bf" : "#ef4444" }
                            Text {
                                text: ({mic: "میکروفن", stt: "شنیدن", tts: "صداسازی", ai: "هوش", wake: "بیداری"})[service] || service
                                color: win.textDim; font.pixelSize: 11
                            }
                        }
                        HoverHandler { id: statusHover }
                        ToolTip.visible: statusHover.hovered
                        ToolTip.text: detail
                        ToolTip.delay: 300
                    }
                }
            }
        }

        // -------- body --------
        RowLayout {
            Layout.fillWidth: true
            Layout.fillHeight: true
            spacing: 14

            // ===== conversation panel (right in RTL) =====
            Rectangle {
                Layout.fillHeight: true
                Layout.preferredWidth: 430
                Layout.minimumWidth: 330
                radius: 16
                color: Qt.rgba(0.043, 0.078, 0.157, 0.72)
                border.color: win.panelBorder
                border.width: 1

                ColumnLayout {
                    anchors.fill: parent
                    anchors.margins: 12
                    spacing: 8

                    RowLayout {
                        Layout.fillWidth: true
                        Text { text: "گفتگو"; color: win.textMain; font.pixelSize: 15; font.bold: true }
                        Item { Layout.fillWidth: true }
                        Rectangle {
                            Layout.preferredHeight: 28; Layout.preferredWidth: clearRow.implicitWidth + 20
                            radius: 14; color: "transparent"; border.color: win.panelBorder; border.width: 1
                            RowLayout { id: clearRow; anchors.centerIn: parent; spacing: 6
                                Text { text: "پاک کردن"; color: win.textDim; font.pixelSize: 11 }
                            }
                            MouseArea { anchors.fill: parent; onClicked: bridge.clearHistory() }
                            HoverHandler { id: clearHover }
                            ToolTip.visible: clearHover.hovered
                            ToolTip.text: "پاک کردن تاریخچهٔ گفتگو"
                        }
                    }

                    ListView {
                        id: listView
                        Layout.fillWidth: true
                        Layout.fillHeight: true
                        clip: true
                        spacing: 10
                        model: messages
                        ScrollBar.vertical: ScrollBar { policy: ScrollBar.AsNeeded }
                        delegate: Item {
                            width: listView.width
                            height: bubble.implicitHeight + 6
                            Rectangle {
                                id: bubble
                                anchors.right: model.role === "user" ? parent.right : undefined
                                anchors.left: model.role === "user" ? undefined : parent.left
                                anchors.rightMargin: model.role === "user" ? 0 : 40
                                anchors.leftMargin: model.role === "user" ? 40 : 0
                                width: Math.min(implicitText.implicitWidth + 28, listView.width - 50)
                                implicitHeight: bubbleCol.implicitHeight + 18
                                radius: 12
                                color: model.role === "user" ? Qt.rgba(0.13, 0.35, 0.45, 0.55)
                                        : model.role === "system" ? Qt.rgba(0.2, 0.16, 0.05, 0.5)
                                        : Qt.rgba(0.07, 0.12, 0.22, 0.85)
                                border.color: model.role === "user" ? Qt.rgba(0.13, 0.83, 0.93, 0.4)
                                        : model.role === "system" ? "#f59e0b" : win.panelBorder
                                border.width: 1
                                ColumnLayout {
                                    id: bubbleCol
                                    anchors.fill: parent
                                    anchors.margins: 10
                                    spacing: 3
                                    Text {
                                        id: implicitText
                                        text: model.role === "user" ? "تو" : model.role === "system" ? "سیستم" : "جاسم"
                                        color: model.role === "user" ? win.accent : model.role === "system" ? "#f59e0b" : "#7dd3fc"
                                        font.pixelSize: 10; font.bold: true
                                    }
                                    Text {
                                        Layout.fillWidth: true
                                        text: model.text
                                        color: win.textMain
                                        font.pixelSize: 14
                                        wrapMode: Text.Wrap
                                        horizontalAlignment: Text.AlignRight
                                        lineHeight: 1.35
                                    }
                                }
                            }
                        }
                    }

                    // text input
                    RowLayout {
                        Layout.fillWidth: true
                        spacing: 8
                        TextField {
                            id: input
                            Layout.fillWidth: true
                            placeholderText: "اینجا بنویس… (جایگزین صدا)"
                            color: win.textMain
                            placeholderTextColor: win.textDim
                            background: Rectangle {
                                radius: 12; color: "#081120"
                                border.color: input.activeFocus ? win.accent : win.panelBorder
                                border.width: 1
                            }
                            Keys.onReturnPressed: { if (text.trim().length) { bridge.submitText(text); text = "" } }
                            horizontalAlignment: Text.AlignRight
                        }
                        Rectangle {
                            Layout.preferredWidth: 46; Layout.preferredHeight: 46; radius: 23
                            gradient: Gradient {
                                GradientStop { position: 0; color: win.accent }
                                GradientStop { position: 1; color: win.accent2 }
                            }
                            Text { anchors.centerIn: parent; text: "↵"; color: "#04070f"; font.pixelSize: 20; font.bold: true }
                            MouseArea {
                                anchors.fill: parent
                                onClicked: { if (input.text.trim().length) { bridge.submitText(input.text); input.text = "" } }
                            }
                        }
                    }
                }
            }

            // ===== center column: core + visualizer + controls =====
            ColumnLayout {
                Layout.fillWidth: true
                Layout.fillHeight: true
                spacing: 12

                Item { Layout.fillHeight: true }

                // --- AI core ---
                Item {
                    id: coreWrap
                    Layout.alignment: Qt.AlignHCenter
                    Layout.preferredWidth: 300
                    Layout.preferredHeight: 300

                    property real level: Math.max(win.micLvl, win.playLvl)

                    Rectangle { id: corePulse
                        property real flashV: 0
                        function flash() { flashV = 1.0 }
                        anchors.centerIn: parent
                        width: 90 + coreWrap.level * 120 + flashV * 60
                        height: width
                        radius: width / 2
                        color: "transparent"
                        border.color: Qt.rgba(0.13, 0.83, 0.93, 0.35 * (1 - flashV))
                        border.width: 3
                        onFlashVChanged: if (flashV > 0) flashAnim.restart()
                        SequentialAnimation {
                            id: flashAnim
                            NumberAnimation { target: corePulse; property: "flashV"; to: 0; duration: 500 }
                        }
                    }

                    Canvas {
                        id: ring1
                        anchors.fill: parent
                        rotation: 0
                        opacity: 0.9
                        property real segs: 7
                        Behavior on rotation { NumberAnimation { duration: 40 } }
                        onPaint: {
                            const ctx = getContext("2d")
                            ctx.clearRect(0, 0, width, height)
                            const cx = width / 2, cy = height / 2, r = Math.min(width, height) / 2 - 6
                            ctx.lineWidth = 3
                            ctx.strokeStyle = win.accent
                            for (let i = 0; i < segs; i++) {
                                const a0 = (i / segs) * 2 * Math.PI
                                const a1 = a0 + (2 * Math.PI / segs) * 0.55
                                ctx.beginPath(); ctx.arc(cx, cy, r, a0, a1); ctx.stroke()
                            }
                        }
                        RotationAnimation on rotation {
                            loops: Animation.Infinite
                            running: true
                            from: 0; to: 360
                            duration: win.currentState === "speaking" ? 2600 : 9000
                        }
                    }
                    Canvas {
                        id: ring2
                        anchors.fill: parent
                        anchors.margins: 26
                        opacity: 0.75
                        property real segs: 12
                        onPaint: {
                            const ctx = getContext("2d")
                            ctx.clearRect(0, 0, width, height)
                            const cx = width / 2, cy = height / 2, r = Math.min(width, height) / 2 - 4
                            ctx.lineWidth = 2
                            ctx.strokeStyle = win.accent2
                            for (let i = 0; i < segs; i++) {
                                const a0 = (i / segs) * 2 * Math.PI
                                const a1 = a0 + (2 * Math.PI / segs) * 0.4
                                ctx.beginPath(); ctx.arc(cx, cy, r, a0, a1); ctx.stroke()
                            }
                        }
                        RotationAnimation on rotation {
                            loops: Animation.Infinite
                            running: true
                            from: 360; to: 0
                            duration: win.currentState === "listening" ? 3200 : 12000
                        }
                    }
                    Canvas {
                        id: ring3
                        anchors.fill: parent
                        anchors.margins: 62
                        opacity: 0.6
                        onPaint: {
                            const ctx = getContext("2d")
                            ctx.clearRect(0, 0, width, height)
                            const cx = width / 2, cy = height / 2, r = Math.min(width, height) / 2
                            ctx.lineWidth = 1
                            ctx.strokeStyle = "#16304f"
                            ctx.beginPath(); ctx.arc(cx, cy, r, 0, 2 * Math.PI); ctx.stroke()
                        }
                    }
                    // orb
                    Rectangle {
                        anchors.centerIn: parent
                        width: 84; height: 84; radius: 42
                        gradient: Gradient {
                            GradientStop { position: 0; color: Qt.lighter(win.stateColor, 1.4) }
                            GradientStop { position: 1; color: Qt.darker(win.stateColor, 1.6) }
                        }
                        SequentialAnimation on scale {
                            loops: Animation.Infinite
                            running: win.currentState !== "idle"
                            NumberAnimation { to: 1.06 + coreWrap.level * 0.25; duration: 700; easing.type: Easing.InOutQuad }
                            NumberAnimation { to: 1.0; duration: 700; easing.type: Easing.InOutQuad }
                        }
                        Rectangle { anchors.centerIn: parent; width: 30; height: 30; radius: 15; color: "#04070f"; opacity: 0.85 }
                        Text {
                            anchors.centerIn: parent
                            text: "ج"
                            color: win.stateColor
                            font.pixelSize: 26; font.bold: true
                        }
                    }
                }

                // --- live waveform bars ---
                Item {
                    Layout.alignment: Qt.AlignHCenter
                    Layout.preferredWidth: Math.min(parent.width - 80, 640)
                    Layout.preferredHeight: 84
                    Row {
                        anchors.centerIn: parent
                        spacing: 4
                        Repeater {
                            model: 40
                            delegate: Rectangle {
                                required property int index
                                width: 7; radius: 3.5
                                color: Qt.rgba(0.13, 0.83, 0.93, 0.85)
                                property real seed: index * 0.37
                                property real target: {
                                    const lvl = Math.max(win.micLvl, win.playLvl * 1.1)
                                    const wob = 0.35 + 0.65 * Math.abs(Math.sin((win.currentTime || 0) * 2.2 + seed * 3.1))
                                    return 6 + lvl * 70 * wob + lvl * 10
                                }
                                height: target
                                anchors.bottom: parent.bottom
                                Behavior on height { NumberAnimation { duration: 90; easing.type: Easing.OutQuad } }
                            }
                        }
                    }
                }

                Text {
                    Layout.alignment: Qt.AlignHCenter
                    text: win.stateLabels[win.currentState] || ""
                    color: win.stateColor
                    font.pixelSize: 18
                    font.bold: true
                }
                Text {
                    Layout.alignment: Qt.AlignHCenter
                    text: win.currentState === "wake_monitoring" ? "«هی جاسم» بگو تا فعال شم" :
                          win.currentState === "listening" ? "صحبتو بکش، هر وقت آماده بودی صبر می‌کنم…" :
                          win.currentState === "speaking" ? "«هی جاسم» بگو یا دکمهٔ توقف رو بزن تا قطع کنم" : " "
                    color: win.textDim
                    font.pixelSize: 12
                }

                // --- controls ---
                RowLayout {
                    Layout.alignment: Qt.AlignHCenter
                    spacing: 18

                    // stop speaking
                    Rectangle {
                        width: 56; height: 56; radius: 28
                        color: "#101a30"; border.color: "#ef4444"; border.width: 1.5
                        Text { anchors.centerIn: parent; text: "◼"; color: "#ef4444"; font.pixelSize: 18 }
                        MouseArea { anchors.fill: parent; onClicked: bridge.stopSpeaking() }
                        HoverHandler { id: stopHover }
                        ToolTip.visible: stopHover.hovered
                        ToolTip.text: "توقف پخش صدا"
                    }

                    // main mic button
                    Rectangle {
                        width: 84; height: 84; radius: 42
                        gradient: Gradient {
                            GradientStop { position: 0; color: win.currentState === "listening" || win.currentState === "speaking" ? "#f97316" : win.accent }
                            GradientStop { position: 1; color: win.currentState === "listening" || win.currentState === "speaking" ? "#ef4444" : win.accent2 }
                        }
                        scale: micArea.pressed ? 0.94 : 1.0
                        Behavior on scale { NumberAnimation { duration: 100 } }
                        Text { anchors.centerIn: parent; text: win.currentState === "listening" ? "◼" : "🎙"; font.pixelSize: 30 }
                        MouseArea { id: micArea; anchors.fill: parent; onClicked: bridge.pushToTalk() }
                        HoverHandler { id: micHover }
                        ToolTip.visible: micHover.hovered
                        ToolTip.text: "شروع/پایان مکالمه (Push-to-talk)"
                        RotationAnimation on rotation {
                            loops: Animation.Infinite
                            running: win.currentState === "listening"
                            from: 0; to: 360; duration: 24000
                        }
                    }

                    // mute
                    Rectangle {
                        width: 56; height: 56; radius: 28
                        color: "#101a30"; border.color: win.panelBorder; border.width: 1.5
                        Text { anchors.centerIn: parent; text: "🎙"; color: win.textDim; font.pixelSize: 18; opacity: 0.8 }
                        MouseArea { anchors.fill: parent; onClicked: bridge.toggleMic() }
                        HoverHandler { id: muteHover }
                        ToolTip.visible: muteHover.hovered
                        ToolTip.text: "قطع/وصل میکروفن (بی‌صدا)"
                    }

                    // repeat
                    Rectangle {
                        width: 56; height: 56; radius: 28
                        color: "#101a30"; border.color: win.panelBorder; border.width: 1.5
                        Text { anchors.centerIn: parent; text: "↻"; color: win.textDim; font.pixelSize: 22 }
                        MouseArea { anchors.fill: parent; onClicked: bridge.repeatLast() }
                        HoverHandler { id: repHover }
                        ToolTip.visible: repHover.hovered
                        ToolTip.text: "تکرار آخرین جواب"
                    }

                    // settings
                    Rectangle {
                        width: 56; height: 56; radius: 28
                        color: "#101a30"; border.color: win.panelBorder; border.width: 1.5
                        Text { anchors.centerIn: parent; text: "⚙"; color: win.textDim; font.pixelSize: 22 }
                        MouseArea { anchors.fill: parent; onClicked: settingsDrawer.visible = !settingsDrawer.visible }
                    }
                }

                Item { Layout.fillHeight: true }
            }

            // ===== settings drawer (left in RTL) =====
            Rectangle {
                id: settingsDrawer
                visible: false
                Layout.fillHeight: true
                Layout.preferredWidth: visible ? 340 : 0
                Behavior on Layout.preferredWidth { NumberAnimation { duration: 180 } }
                clip: true
                radius: 16
                color: Qt.rgba(0.043, 0.078, 0.157, 0.92)
                border.color: win.panelBorder
                border.width: 1

                ColumnLayout {
                    anchors.fill: parent
                    anchors.margins: 16
                    spacing: 10

                    RowLayout {
                        Text { text: "تنظیمات"; color: win.textMain; font.pixelSize: 16; font.bold: true }
                        Item { Layout.fillWidth: true }
                        Rectangle {
                            Layout.preferredWidth: 30; Layout.preferredHeight: 30; radius: 15
                            color: "#101a30"
                            Text { anchors.centerIn: parent; text: "✕"; color: win.textDim }
                            MouseArea { anchors.fill: parent; onClicked: settingsDrawer.visible = false }
                        }
                    }

                    ScrollView {
                        Layout.fillWidth: true
                        Layout.fillHeight: true
                        contentWidth: availableWidth
                        ColumnLayout {
                            width: parent.width
                            spacing: 14

                            // TTS engine
                            Text { text: "موتور صداسازی"; color: win.textDim; font.pixelSize: 12 }
                            RowLayout {
                                Layout.fillWidth: true
                                spacing: 8
                                ComboBox {
                                    id: ttsEngineBox
                                    Layout.fillWidth: true
                                    model: ["edge", "piper"]
                                    currentIndex: 0
                                    onActivated: bridge.setSetting("tts.engine", currentText)
                                }
                            }
                            Text { text: "بلندی گفتار (edge rate)"; color: win.textDim; font.pixelSize: 12 }
                            Slider {
                                id: rateSlider
                                Layout.fillWidth: true
                                from: -50; to: 50; value: 0
                                onMoved: bridge.setSetting("tts.edge_rate", (value >= 0 ? "+" : "") + Math.round(value) + "%")
                            }

                            Rectangle { Layout.fillWidth: true; height: 1; color: win.panelBorder }

                            // personality
                            Text { text: "شخصیت جاسم"; color: win.textMain; font.bold: true; font.pixelSize: 13 }
                            Text { text: "کنایه و شوخی"; color: win.textDim; font.pixelSize: 12 }
                            Slider { Layout.fillWidth: true; from: 0; to: 1; value: 0.6
                                onMoved: bridge.setSetting("personality.sarcasm", value) }
                            Text { text: "صمیمیت"; color: win.textDim; font.pixelSize: 12 }
                            Slider { Layout.fillWidth: true; from: 0; to: 1; value: 0.8
                                onMoved: bridge.setSetting("personality.warmth", value) }
                            Text { text: "رسمیت"; color: win.textDim; font.pixelSize: 12 }
                            Slider { Layout.fillWidth: true; from: 0; to: 1; value: 0.2
                                onMoved: bridge.setSetting("personality.formality", value) }
                            Text { text: "طول پاسخ"; color: win.textDim; font.pixelSize: 12 }
                            ComboBox {
                                Layout.fillWidth: true
                                model: ["short", "medium", "detailed"]
                                currentIndex: 0
                                onActivated: bridge.setSetting("personality.response_length", currentText)
                            }

                            Rectangle { Layout.fillWidth: true; height: 1; color: win.panelBorder }

                            // wake word
                            Text { text: "گوش دادن همیشگی"; color: win.textMain; font.bold: true; font.pixelSize: 13 }
                            Switch {
                                checked: true
                                onToggled: bridge.setSetting("wake.enabled", checked)
                                contentItem: Text {
                                    text: "فعال («هی جاسم»)"
                                    color: win.textMain
                                    leftPadding: 8
                                    verticalAlignment: Text.AlignVCenter
                                }
                            }
                            Switch {
                                checked: true
                                onToggled: bridge.setSetting("wake.barge_in", checked)
                                contentItem: Text {
                                    text: "قطع صدا با گفتن «هی جاسم»"
                                    color: win.textMain
                                    leftPadding: 8
                                    verticalAlignment: Text.AlignVCenter
                                }
                            }
                            Text {
                                Layout.fillWidth: true
                                text: "عبارت‌های بیداری: «هی جاسم»، «سلام جاسم»، «جاسم»، Hey JASEM"
                                color: win.textDim; font.pixelSize: 11; wrapMode: Text.Wrap
                            }

                            Rectangle { Layout.fillWidth: true; height: 1; color: win.panelBorder }

                            // privacy
                            Text { text: "حریم خصوصی"; color: win.textMain; font.bold: true; font.pixelSize: 13 }
                            Switch {
                                checked: false
                                onToggled: bridge.setSetting("ai.memory_enabled", checked)
                                contentItem: Text { text: "حفظ حافظهٔ بلندمدت"; color: win.textMain; leftPadding: 8; verticalAlignment: Text.AlignVCenter }
                            }
                            RowLayout {
                                Layout.fillWidth: true
                                spacing: 8
                                Button {
                                    text: "پاک کردن حافظه"
                                    Layout.fillWidth: true
                                    onClicked: bridge.forgetMemory()
                                }
                                Button {
                                    text: "توقف اضطراری"
                                    Layout.fillWidth: true
                                    onClicked: bridge.emergencyStop()
                                }
                            }

                            Rectangle { Layout.fillWidth: true; height: 1; color: win.panelBorder }

                            // system
                            Text { text: "سیستم"; color: win.textMain; font.bold: true; font.pixelSize: 13 }
                            Switch {
                                checked: false
                                onToggled: bridge.setSetting("system.autostart", checked)
                                contentItem: Text { text: "اجرا با روشن شدن ویندوز"; color: win.textMain; leftPadding: 8; verticalAlignment: Text.AlignVCenter }
                            }

                            Rectangle { Layout.fillWidth: true; height: 1; color: win.panelBorder }

                            // hotkeys
                            Text { text: "کلیدهای میان‌بر سراسری"; color: win.textMain; font.bold: true; font.pixelSize: 13 }
                            TextField {
                                Layout.fillWidth: true
                                text: "ctrl+alt+j"
                                placeholderText: "میان‌بر مکالمه (مثلاً ctrl+alt+j)"
                                color: win.textMain
                                background: Rectangle { radius: 10; color: "#081120"; border.color: win.panelBorder }
                                horizontalAlignment: Text.AlignRight
                                onEditingFinished: {
                                    bridge.setSetting("ui.hotkey_ptt", text)
                                    toast.show("میان‌بر مکالمه ذخیره شد؛ بعد از اجرای دوباره فعال می‌شود.")
                                }
                            }
                            TextField {
                                Layout.fillWidth: true
                                text: "ctrl+alt+m"
                                placeholderText: "میان‌بر بی‌صدا (مثلاً ctrl+alt+m)"
                                color: win.textMain
                                background: Rectangle { radius: 10; color: "#081120"; border.color: win.panelBorder }
                                horizontalAlignment: Text.AlignRight
                                onEditingFinished: {
                                    bridge.setSetting("ui.hotkey_mute", text)
                                    toast.show("میان‌بر بی‌صدا ذخیره شد؛ بعد از اجرای دوباره فعال می‌شود.")
                                }
                            }

                            Rectangle { Layout.fillWidth: true; height: 1; color: win.panelBorder }
                            Text {
                                Layout.fillWidth: true
                                wrapMode: Text.Wrap
                                color: win.textDim; font.pixelSize: 11
                                text: "کلیدهای API در فایل .env پروژه تنظیم می‌شوند و هرگز در برنامه ذخیره یا نمایش داده نمی‌شوند."
                            }
                        }
                    }
                }
            }
        }
    }

    // helper for bar animation timing
    property real currentTime: 0
    Timer { interval: 90; repeat: true; running: true; onTriggered: win.currentTime = Date.now() / 1000 }

    // ================= confirmation dialog =================
    Rectangle {
        id: confirmOverlay
        visible: win.confirmationOpen
        anchors.fill: parent
        z: 50
        color: Qt.rgba(0, 0, 0, 0.6)

        Rectangle {
            anchors.centerIn: parent
            width: 460
            height: confirmCol.implicitHeight + 40
            radius: 18
            color: "#0b1428"
            border.color: "#f59e0b"
            border.width: 1.5

            ColumnLayout {
                id: confirmCol
                anchors.fill: parent
                anchors.margins: 20
                spacing: 14
                Text {
                    text: "تأیید عملیات"
                    color: "#f59e0b"; font.pixelSize: 16; font.bold: true
                }
                Text {
                    Layout.fillWidth: true
                    text: win.confirmationText
                    color: win.textMain; font.pixelSize: 15
                    wrapMode: Text.Wrap
                    lineHeight: 1.4
                }
                RowLayout {
                    Layout.fillWidth: true
                    spacing: 12
                    Rectangle {
                        Layout.fillWidth: true; Layout.preferredHeight: 46; radius: 12
                        color: "#101a30"; border.color: "#ef4444"; border.width: 1
                        Text { anchors.centerIn: parent; text: "نه، لغو"; color: "#ef4444"; font.pixelSize: 15; font.bold: true }
                        MouseArea { anchors.fill: parent; onClicked: bridge.confirmAction(false) }
                    }
                    Rectangle {
                        Layout.fillWidth: true; Layout.preferredHeight: 46; radius: 12
                        gradient: Gradient {
                            GradientStop { position: 0; color: "#14b8a6" }
                            GradientStop { position: 1; color: "#0ea5e9" }
                        }
                        Text { anchors.centerIn: parent; text: "بله، انجام بده"; color: "#04070f"; font.pixelSize: 15; font.bold: true }
                        MouseArea { anchors.fill: parent; onClicked: bridge.confirmAction(true) }
                    }
                }
            }
        }
    }

    // ================= toast =================
    Rectangle {
        id: toast
        property string msg: ""
        anchors.horizontalCenter: parent.horizontalCenter
        anchors.bottom: parent.bottom
        anchors.bottomMargin: 24
        width: toastText.implicitWidth + 40
        height: 44
        radius: 22
        color: Qt.rgba(0.043, 0.078, 0.157, 0.95)
        border.color: win.accent
        border.width: 1
        visible: opacity > 0.01
        opacity: 0
        z: 60
        Text { id: toastText; anchors.centerIn: parent; text: toast.msg; color: win.textMain; font.pixelSize: 13 }
        function show(text) {
            toast.msg = text
            toast.opacity = 1
            toastTimer.restart()
        }
        Behavior on opacity { NumberAnimation { duration: 250 } }
        Timer { id: toastTimer; interval: 3200; onTriggered: toast.opacity = 0 }
    }
}
