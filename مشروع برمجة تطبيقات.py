import socket
import threading
from PyQt5.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLineEdit, QTextEdit, QLabel, QTabWidget, QComboBox
)
from PyQt5.QtCore import Qt

# ============================
# جدول الأقران (اسم → IP, Port)
# ============================
PEERS = {
    "Hamzah":  ("192.168.30.130", 5000),   # جهازك أنت (Hamzah)
    "Ali":     ("192.168.30.150", 5000),
    "Mohamed": ("192.168.30.140", 5000),
    "Maryam":  ("192.168.30.141", 5000)
}

connections = {}
running = True

# ============================
# إيجاد اسم من خلال IP
# ============================
def get_name_from_ip(ip):
    for name, (peer_ip, _) in PEERS.items():
        if peer_ip == ip:
            return name
    return "مستخدم غير معروف"

# ============================
# استقبال الرسائل
# ============================
def receive_from_peer(name, sock, gui):
    sock.settimeout(0.1)
    global running
    while running:
        try:
            data = sock.recv(2048)
            if not data:
                break

            msg = data.decode()

            if msg.startswith("[GROUP]"):
                clean = msg.replace("[GROUP]", "")
                gui.log_group(name, clean)
            else:
                gui.log_private(name, msg)

        except socket.timeout:
            continue
        except:
            break

    sock.close()
    connections.pop(name, None)

# ============================
# الاتصال بشخص معين
# ============================
def connect_to_peer(name, gui):
    if name in connections:
        return connections[name]

    if name not in PEERS:
        gui.log_private("النظام", "❌ الاسم غير موجود في جدول الأقران")
        return None

    ip, port = PEERS[name]

    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.connect((ip, port))
        sock.settimeout(0.1)

        connections[name] = sock

        threading.Thread(
            target=receive_from_peer,
            args=(name, sock, gui),
            daemon=True
        ).start()

        return sock

    except:
        gui.log_private("النظام", f"❌ فشل الاتصال بـ {name}")
        return None

# ============================
# Thread الاستماع
# ============================
def listen_thread(gui, my_port=5000):
    global running
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind(("", my_port))
    server.listen(5)

    gui.log_group("النظام", "🔊 جاهز لاستقبال رسائل المجموعة")
    gui.log_private("النظام", "🔊 جاهز لاستقبال الرسائل الفردية")

    while running:
        try:
            client_sock, addr = server.accept()
            ip = addr[0]
            peer_name = get_name_from_ip(ip)

            connections[peer_name] = client_sock

            threading.Thread(
                target=receive_from_peer,
                args=(peer_name, client_sock, gui),
                daemon=True
            ).start()

        except:
            continue

    server.close()

# ============================
# واجهة PyQt5
# ============================
class ChatGUI(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("P2P Chat - Group & Private (Colored)")
        self.setGeometry(200, 200, 700, 500)

        main_layout = QVBoxLayout()
        self.tabs = QTabWidget()
        main_layout.addWidget(self.tabs)

        self.group_tab = QWidget()
        self.private_tab = QWidget()

        self.tabs.addTab(self.group_tab, "Group Chat")
        self.tabs.addTab(self.private_tab, "Private Chat")

        # ============================
        # Group Chat
        # ============================
        group_layout = QVBoxLayout()

        self.group_chat_box = QTextEdit()
        self.group_chat_box.setReadOnly(True)
        group_layout.addWidget(self.group_chat_box)

        h_group = QHBoxLayout()
        h_group.addWidget(QLabel("الرسالة:"))
        self.group_entry_msg = QLineEdit()
        self.group_entry_msg.setPlaceholderText("اكتب رسالة للمجموعة...")
        h_group.addWidget(self.group_entry_msg)
        group_layout.addLayout(h_group)

        btn_group_send = QPushButton("إرسال للمجموعة")
        btn_group_send.clicked.connect(self.send_group_message)
        group_layout.addWidget(btn_group_send)

        self.group_tab.setLayout(group_layout)

        # ============================
        # Private Chat
        # ============================
        private_layout = QVBoxLayout()

        self.private_chat_box = QTextEdit()
        self.private_chat_box.setReadOnly(True)
        private_layout.addWidget(self.private_chat_box)

        h_name = QHBoxLayout()
        h_name.addWidget(QLabel("اختر الاسم:"))
        self.private_name_combo = QComboBox()
        self.private_name_combo.addItems(["Ali", "Mohamed", "Maryam"])
        h_name.addWidget(self.private_name_combo)
        private_layout.addLayout(h_name)

        h_msg = QHBoxLayout()
        h_msg.addWidget(QLabel("الرسالة:"))
        self.private_entry_msg = QLineEdit()
        self.private_entry_msg.setPlaceholderText("اكتب رسالة فردية...")
        h_msg.addWidget(self.private_entry_msg)
        private_layout.addLayout(h_msg)

        btn_private_send = QPushButton("إرسال فردي")
        btn_private_send.clicked.connect(self.send_private_message)
        private_layout.addWidget(btn_private_send)

        self.private_tab.setLayout(private_layout)

        self.setLayout(main_layout)

    # ============================
    # دوال تسجيل الرسائل مع ألوان
    # ============================
    def log_group(self, sender, msg):
        if sender == "أنت":
            color = "#0078FF"
        elif sender == "النظام":
            color = "#555555"
        else:
            color = "#8A2BE2"

        html = (
            f"<span style='color:{color}; font-weight:bold;'>{sender}:</span> "
            f"<span style='color:{color};'>{msg}</span>"
        )
        self.group_chat_box.append(html)

    def log_private(self, sender, msg):
        if sender == "أنت":
            color = "#0078FF"
        elif sender == "النظام":
            color = "#555555"
        else:
            color = "#009900"

        html = (
            f"<span style='color:{color}; font-weight:bold;'>{sender}:</span> "
            f"<span style='color:{color};'>{msg}</span>"
        )
        self.private_chat_box.append(html)

    # ============================
    # إرسال للمجموعة
    # ============================
    def send_group_message(self):
        msg = self.group_entry_msg.text().strip()
        if not msg:
            return

        sender = "Hamzah"
        self.log_group("أنت", msg)

        for name in PEERS:
            if name == sender:
                continue
            sock = connect_to_peer(name, self)
            if sock:
                try:
                    sock.send(f"[GROUP]{msg}".encode())
                except:
                    self.log_group("النظام", f"❌ فشل إرسال الرسالة إلى {name}")

        self.group_entry_msg.clear()

    # ============================
    # إرسال فردي
    # ============================
    def send_private_message(self):
        name = self.private_name_combo.currentText()
        msg = self.private_entry_msg.text().strip()

        if not msg:
            return

        sock = connect_to_peer(name, self)
        if sock:
            try:
                sock.send(msg.encode())
                self.log_private("أنت", msg)
            except:
                self.log_private("النظام", "❌ فشل الإرسال")

        self.private_entry_msg.clear()

# ============================
# main
# ============================
def main():
    app = QApplication([])

    gui = ChatGUI()
    gui.show()

    threading.Thread(target=listen_thread, args=(gui, 5000), daemon=True).start()

    app.exec_()

    global running
    running = False

if __name__ == "__main__":
    main()
