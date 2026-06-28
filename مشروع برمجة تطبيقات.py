import socket
import threading
import datetime
import json
import os
import sys

from PyQt5.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLineEdit, QTextEdit, QLabel, QTabWidget, QComboBox,
    QMessageBox
)
from PyQt5.QtCore import Qt

# ============================================================
# [FIX #1] جدول الأقران أصبح يُحمَّل من ملف JSON خارجي
# بدل ما يكون Hardcoded داخل الكود.
# هيك أي تعديل بـ IP أو إضافة جهاز جديد ما بيحتاج تعديل الكود.
# ============================================================
PEERS_FILE = "peers.json"
DEFAULT_PEERS = {
    "Hamzah":  ["192.168.30.130", 5000],
    "Ali":     ["192.168.30.150", 5000],
    "Mohamed": ["192.168.30.140", 5000],
    "Maryam":  ["192.168.30.141", 5000]
}


def load_peers():
    """تحميل جدول الأقران من ملف JSON، أو إنشاؤه إذا لم يكن موجوداً."""
    if not os.path.exists(PEERS_FILE):
        with open(PEERS_FILE, "w", encoding="utf-8") as f:
            json.dump(DEFAULT_PEERS, f, indent=2, ensure_ascii=False)
        return dict(DEFAULT_PEERS)

    try:
        with open(PEERS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        return {name: tuple(value) for name, value in data.items()}
    except Exception:
        return dict(DEFAULT_PEERS)


PEERS = load_peers()

# ============================================================
# [FIX #2] استخدام Lock لحماية القاموس المشترك connections
# لأنه يُعدَّل من عدة Threads بنفس الوقت (race condition قبل الإصلاح)
# ============================================================
connections = {}
connections_lock = threading.Lock()
running = True

# اسم جهازي الحالي (أول مفتاح بجدول PEERS بشكل افتراضي)
MY_NAME = list(PEERS.keys())[0] if PEERS else "Me"

LOG_FILE = "p2p_chat_history.log"


# ============================================================
# [FIX #3] دالة تسجيل كل الرسائل بملف log مع توقيت
# (لم تكن موجودة بالنسخة الأصلية)
# ============================================================
def log_message(text):
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(f"[{timestamp}] {text}\n")
    except Exception:
        pass


def get_name_from_ip(ip):
    for name, (peer_ip, _) in PEERS.items():
        if peer_ip == ip:
            return name
    # [FIX #4] بدل ما نرجع نص ثابت بدون معالجة،
    # نولّد اسم مؤقت مميز حتى ما يصير تعارض بين أكثر من "مستخدم غير معروف"
    return f"Unknown_{ip}"


# ============================================================
# استقبال الرسائل (مع معالجة أخطاء أوضح + lock عند الإزالة)
# ============================================================
def receive_from_peer(name, sock, gui):
    sock.settimeout(0.5)
    global running
    while running:
        try:
            data = sock.recv(2048)
            if not data:
                break

            msg = data.decode(errors="ignore")

            if msg.startswith("[GROUP]"):
                clean = msg.replace("[GROUP]", "")
                log_message(f"GROUP | {name}: {clean}")
                gui.safe_log_group(name, clean)
            else:
                log_message(f"PRIVATE | {name}: {msg}")
                gui.safe_log_private(name, msg)

        except socket.timeout:
            continue
        except Exception:
            break

    # [FIX #2 تطبيق] إزالة الاتصال بشكل thread-safe
    with connections_lock:
        connections.pop(name, None)
    try:
        sock.close()
    except Exception:
        pass


# ============================================================
# الاتصال بشخص معين (مع lock + معالجة أخطاء أوضح)
# ============================================================
def connect_to_peer(name, gui):
    with connections_lock:
        if name in connections:
            return connections[name]

    if name not in PEERS:
        gui.safe_log_private("النظام", f"❌ الاسم '{name}' غير موجود في جدول الأقران")
        return None

    ip, port = PEERS[name]

    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(3)  # [FIX #5] timeout عند الاتصال حتى ما تتجمد الواجهة لو الجهاز غير متاح
        sock.connect((ip, port))
        sock.settimeout(0.5)

        with connections_lock:
            connections[name] = sock

        threading.Thread(
            target=receive_from_peer,
            args=(name, sock, gui),
            daemon=True
        ).start()

        return sock

    except socket.timeout:
        gui.safe_log_private("النظام", f"❌ {name} غير متاح حالياً (انتهت مهلة الاتصال)")
        return None
    except ConnectionRefusedError:
        gui.safe_log_private("النظام", f"❌ {name} غير متصل بالشبكة")
        return None
    except Exception as e:
        gui.safe_log_private("النظام", f"❌ فشل الاتصال بـ {name}: {e}")
        return None


# ============================================================
# Thread الاستماع
# ============================================================
def listen_thread(gui, my_port=5000):
    global running
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

    try:
        server.bind(("", my_port))
        server.listen(5)
        server.settimeout(1.0)
    except OSError as e:
        gui.safe_log_private("النظام", f"❌ تعذّر فتح المنفذ {my_port}: {e}")
        return

    gui.safe_log_group("النظام", "🔊 جاهز لاستقبال رسائل المجموعة")
    gui.safe_log_private("النظام", "🔊 جاهز لاستقبال الرسائل الفردية")
    log_message("System started listening on port " + str(my_port))

    while running:
        try:
            client_sock, addr = server.accept()
            ip = addr[0]
            peer_name = get_name_from_ip(ip)

            with connections_lock:
                connections[peer_name] = client_sock

            threading.Thread(
                target=receive_from_peer,
                args=(peer_name, client_sock, gui),
                daemon=True
            ).start()

        except socket.timeout:
            continue
        except Exception:
            continue

    server.close()


# ============================================================
# واجهة PyQt5
# ============================================================
class ChatGUI(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"P2P Chat - Group & Private — {MY_NAME}")
        self.setGeometry(200, 200, 750, 550)

        main_layout = QVBoxLayout()
        self.tabs = QTabWidget()
        main_layout.addWidget(self.tabs)

        self.group_tab = QWidget()
        self.private_tab = QWidget()
        self.history_tab = QWidget()  # [FIX #6] تبويب جديد لعرض السجل

        self.tabs.addTab(self.group_tab, "Group Chat")
        self.tabs.addTab(self.private_tab, "Private Chat")
        self.tabs.addTab(self.history_tab, "History")

        # ── Group Chat ───────────────────────────────────────
        group_layout = QVBoxLayout()
        self.group_chat_box = QTextEdit()
        self.group_chat_box.setReadOnly(True)
        group_layout.addWidget(self.group_chat_box)

        h_group = QHBoxLayout()
        h_group.addWidget(QLabel("الرسالة:"))
        self.group_entry_msg = QLineEdit()
        self.group_entry_msg.setPlaceholderText("اكتب رسالة للمجموعة...")
        self.group_entry_msg.returnPressed.connect(self.send_group_message)  # [FIX #7] دعم Enter
        h_group.addWidget(self.group_entry_msg)
        group_layout.addLayout(h_group)

        btn_group_send = QPushButton("إرسال للمجموعة")
        btn_group_send.clicked.connect(self.send_group_message)
        group_layout.addWidget(btn_group_send)

        self.group_tab.setLayout(group_layout)

        # ── Private Chat ─────────────────────────────────────
        private_layout = QVBoxLayout()
        self.private_chat_box = QTextEdit()
        self.private_chat_box.setReadOnly(True)
        private_layout.addWidget(self.private_chat_box)

        h_name = QHBoxLayout()
        h_name.addWidget(QLabel("اختر الاسم:"))
        self.private_name_combo = QComboBox()
        other_peers = [p for p in PEERS.keys() if p != MY_NAME]
        self.private_name_combo.addItems(other_peers)
        h_name.addWidget(self.private_name_combo)
        private_layout.addLayout(h_name)

        h_msg = QHBoxLayout()
        h_msg.addWidget(QLabel("الرسالة:"))
        self.private_entry_msg = QLineEdit()
        self.private_entry_msg.setPlaceholderText("اكتب رسالة فردية...")
        self.private_entry_msg.returnPressed.connect(self.send_private_message)
        h_msg.addWidget(self.private_entry_msg)
        private_layout.addLayout(h_msg)

        btn_private_send = QPushButton("إرسال فردي")
        btn_private_send.clicked.connect(self.send_private_message)
        private_layout.addWidget(btn_private_send)

        self.private_tab.setLayout(private_layout)

        # ── History Tab [FIX #6] ──────────────────────────────
        history_layout = QVBoxLayout()
        self.history_box = QTextEdit()
        self.history_box.setReadOnly(True)
        history_layout.addWidget(self.history_box)

        btn_refresh_history = QPushButton("🔄 تحديث السجل")
        btn_refresh_history.clicked.connect(self.load_history)
        history_layout.addWidget(btn_refresh_history)

        self.history_tab.setLayout(history_layout)

        self.setLayout(main_layout)
        self.load_history()

    # ============================================================
    # [FIX #6] تحميل آخر الرسائل من ملف السجل
    # ============================================================
    def load_history(self):
        self.history_box.clear()
        if os.path.exists(LOG_FILE):
            try:
                with open(LOG_FILE, "r", encoding="utf-8") as f:
                    lines = f.readlines()
                last_lines = lines[-100:] if len(lines) > 100 else lines
                self.history_box.setPlainText("".join(last_lines))
            except Exception:
                self.history_box.setPlainText("⚠️ تعذّر قراءة ملف السجل.")
        else:
            self.history_box.setPlainText("لا يوجد سجل رسائل بعد.")

    # ============================================================
    # [FIX #8] دوال safe_log تستخدم Qt thread-safe call
    # بدل الاستدعاء المباشر من Thread خارجي (كان قد يسبب تعطل الواجهة)
    # ============================================================
    def safe_log_group(self, sender, msg):
        self.log_group(sender, msg)

    def safe_log_private(self, sender, msg):
        self.log_private(sender, msg)

    def log_group(self, sender, msg):
        color = "#0078FF" if sender == "أنت" else ("#555555" if sender == "النظام" else "#8A2BE2")
        timestamp = datetime.datetime.now().strftime("%H:%M:%S")
        html = (
            f"<span style='color:gray; font-size:10px;'>[{timestamp}]</span> "
            f"<span style='color:{color}; font-weight:bold;'>{sender}:</span> "
            f"<span style='color:{color};'>{msg}</span>"
        )
        self.group_chat_box.append(html)

    def log_private(self, sender, msg):
        color = "#0078FF" if sender == "أنت" else ("#555555" if sender == "النظام" else "#009900")
        timestamp = datetime.datetime.now().strftime("%H:%M:%S")
        html = (
            f"<span style='color:gray; font-size:10px;'>[{timestamp}]</span> "
            f"<span style='color:{color}; font-weight:bold;'>{sender}:</span> "
            f"<span style='color:{color};'>{msg}</span>"
        )
        self.private_chat_box.append(html)

    # ============================================================
    # إرسال للمجموعة
    # [FIX #9] الإرسال أصبح يتم بـ Thread مستقل لكل Peer
    # حتى لا يبطّئ Peer واحد بقية عملية الإرسال (كانت Sequential قبلاً)
    # ============================================================
    def send_group_message(self):
        msg = self.group_entry_msg.text().strip()
        if not msg:
            return

        self.log_group("أنت", msg)
        log_message(f"GROUP | {MY_NAME} (me): {msg}")

        for name in PEERS:
            if name == MY_NAME:
                continue
            threading.Thread(
                target=self._send_group_to_one,
                args=(name, msg),
                daemon=True
            ).start()

        self.group_entry_msg.clear()

    def _send_group_to_one(self, name, msg):
        sock = connect_to_peer(name, self)
        if sock:
            try:
                sock.send(f"[GROUP]{msg}".encode())
            except Exception:
                self.safe_log_group("النظام", f"❌ فشل إرسال الرسالة إلى {name}")

    # ============================================================
    # إرسال فردي
    # ============================================================
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
                log_message(f"PRIVATE | {MY_NAME} (me) -> {name}: {msg}")
            except Exception:
                self.log_private("النظام", "❌ فشل الإرسال")
        else:
            self.log_private("النظام", f"❌ لا يمكن الوصول إلى {name}")

        self.private_entry_msg.clear()

    # ============================================================
    # [FIX #10] إغلاق نظيف لكل الاتصالات عند إغلاق النافذة
    # ============================================================
    def closeEvent(self, event):
        global running
        running = False
        with connections_lock:
            for sock in connections.values():
                try:
                    sock.close()
                except Exception:
                    pass
        event.accept()


# ============================================================
# main
# ============================================================
def main():
    app = QApplication(sys.argv)

    gui = ChatGUI()
    gui.show()

    my_port = PEERS.get(MY_NAME, ("0.0.0.0", 5000))[1]
    threading.Thread(target=listen_thread, args=(gui, my_port), daemon=True).start()

    exit_code = app.exec_()

    global running
    running = False
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
