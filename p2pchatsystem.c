#include <gtk/gtk.h>
#include <arpa/inet.h>
#include <pthread.h>
#include <unistd.h>
#include <string.h>
#include <stdlib.h>
#include <stdio.h>

#define BUFFER_SIZE 1024

// عناصر الواجهة
GtkWidget *window;
GtkWidget *text_view;
GtkWidget *entry_ip;
GtkWidget *entry_port;
GtkWidget *entry_message;
GtkWidget *button_send;
GtkWidget *button_listen;
GtkWidget *button_connect;

GtkTextBuffer *text_buffer;

int sockfd = -1;
int running = 0;
pthread_t recv_thread;

// دالة لإضافة نص إلى صندوق المحادثة من أي Thread
gboolean append_text_to_view(gpointer data) {
    char *msg = (char *)data;
    GtkTextIter end;
    gtk_text_buffer_get_end_iter(text_buffer, &end);
    gtk_text_buffer_insert(text_buffer, &end, msg, -1);
    gtk_text_buffer_insert(text_buffer, &end, "\n", -1);
    free(msg);
    return FALSE;
}

void *receive_thread_func(void *arg) {
    char buffer[BUFFER_SIZE];
    while (running) {
        int bytes = recv(sockfd, buffer, sizeof(buffer) - 1, 0);
        if (bytes <= 0) {
            char *msg = strdup("[!] تم قطع الاتصال من الطرف الآخر.");
            g_idle_add(append_text_to_view, msg);
            running = 0;
            break;
        }
        buffer[bytes] = '\0';

        char *msg = malloc(strlen(buffer) + 30);
        sprintf(msg, "الطرف الآخر: %s", buffer);
        g_idle_add(append_text_to_view, msg);
    }
    return NULL;
}

void start_receive_thread() {
    running = 1;
    pthread_create(&recv_thread, NULL, receive_thread_func, NULL);
}

// Thread للاستماع كخادم (حتى لا تتجمد الواجهة)
void *listen_thread(void *arg) {
    int port = *(int *)arg;
    free(arg);

    int server_fd;
    struct sockaddr_in server_addr, client_addr;
    socklen_t client_len = sizeof(client_addr);

    server_fd = socket(AF_INET, SOCK_STREAM, 0);
    if (server_fd < 0) {
        g_idle_add(append_text_to_view, strdup("خطأ في إنشاء الخادم."));
        return NULL;
    }

    server_addr.sin_family = AF_INET;
    server_addr.sin_addr.s_addr = INADDR_ANY;
    server_addr.sin_port = htons(port);

    if (bind(server_fd, (struct sockaddr *)&server_addr, sizeof(server_addr)) < 0) {
        g_idle_add(append_text_to_view, strdup("خطأ في bind."));
        close(server_fd);
        return NULL;
    }

    if (listen(server_fd, 1) < 0) {
        g_idle_add(append_text_to_view, strdup("خطأ في listen."));
        close(server_fd);
        return NULL;
    }

    char info[100];
    sprintf(info, "[+] في انتظار اتصال على المنفذ %d...", port);
    g_idle_add(append_text_to_view, strdup(info));

    sockfd = accept(server_fd, (struct sockaddr *)&client_addr, &client_len);
    if (sockfd < 0) {
        g_idle_add(append_text_to_view, strdup("خطأ في accept."));
        close(server_fd);
        return NULL;
    }

    g_idle_add(append_text_to_view, strdup("[✓] تم الاتصال بالطرف الآخر (خادم)."));
    close(server_fd);

    start_receive_thread();
    return NULL;
}

// زر الاستماع كخادم
void on_listen_clicked(GtkButton *button, gpointer user_data) {
    if (sockfd != -1 || running) {
        g_idle_add(append_text_to_view, strdup("[!] الاتصال موجود بالفعل."));
        return;
    }

    const char *port_str = gtk_entry_get_text(GTK_ENTRY(entry_port));
    if (strlen(port_str) == 0) {
        g_idle_add(append_text_to_view, strdup("[!] الرجاء إدخال المنفذ."));
        return;
    }

    int port = atoi(port_str);
    if (port <= 0) {
        g_idle_add(append_text_to_view, strdup("[!] منفذ غير صالح."));
        return;
    }

    int *port_ptr = malloc(sizeof(int));
    *port_ptr = port;

    pthread_t t;
    pthread_create(&t, NULL, listen_thread, port_ptr);
    pthread_detach(t);
}

// زر الاتصال كعميل
void on_connect_clicked(GtkButton *button, gpointer user_data) {
    if (sockfd != -1 || running) {
        g_idle_add(append_text_to_view, strdup("[!] الاتصال موجود بالفعل."));
        return;
    }

    const char *ip_str = gtk_entry_get_text(GTK_ENTRY(entry_ip));
    const char *port_str = gtk_entry_get_text(GTK_ENTRY(entry_port));

    if (strlen(ip_str) == 0 || strlen(port_str) == 0) {
        g_idle_add(append_text_to_view, strdup("[!] الرجاء إدخال IP والمنفذ."));
        return;
    }

    int port = atoi(port_str);
    if (port <= 0) {
        g_idle_add(append_text_to_view, strdup("[!] منفذ غير صالح."));
        return;
    }

    struct sockaddr_in server_addr;

    sockfd = socket(AF_INET, SOCK_STREAM, 0);
    if (sockfd < 0) {
        g_idle_add(append_text_to_view, strdup("خطأ في إنشاء العميل."));
        sockfd = -1;
        return;
    }

    server_addr.sin_family = AF_INET;
    server_addr.sin_port = htons(port);
    if (inet_pton(AF_INET, ip_str, &server_addr.sin_addr) <= 0) {
        g_idle_add(append_text_to_view, strdup("[!] IP غير صالح."));
        close(sockfd);
        sockfd = -1;
        return;
    }

    char info[150];
    sprintf(info, "[*] محاولة الاتصال بـ %s:%d...", ip_str, port);
    g_idle_add(append_text_to_view, strdup(info));

    if (connect(sockfd, (struct sockaddr *)&server_addr, sizeof(server_addr)) < 0) {
        g_idle_add(append_text_to_view, strdup("خطأ في الاتصال."));
        close(sockfd);
        sockfd = -1;
        return;
    }

    g_idle_add(append_text_to_view, strdup("[✓] تم الاتصال بالطرف الآخر (عميل)."));

    start_receive_thread();
}

// زر إرسال الرسالة
void on_send_clicked(GtkButton *button, gpointer user_data) {
    if (sockfd == -1 || !running) {
        g_idle_add(append_text_to_view, strdup("[!] لا يوجد اتصال نشط."));
        return;
    }

    const char *msg = gtk_entry_get_text(GTK_ENTRY(entry_message));
    if (strlen(msg) == 0) return;

    send(sockfd, msg, strlen(msg), 0);

    char self_msg[BUFFER_SIZE + 20];
    snprintf(self_msg, sizeof(self_msg), "أنت: %s", msg);
    g_idle_add(append_text_to_view, strdup(self_msg));

    gtk_entry_set_text(GTK_ENTRY(entry_message), "");
}

// عند إغلاق النافذة
void on_window_destroy() {
    running = 0;
    if (sockfd != -1) {
        close(sockfd);
    }
    gtk_main_quit();
}

int main(int argc, char *argv[]) {
    gtk_init(&argc, &argv);

    // إنشاء العناصر
    window = gtk_window_new(GTK_WINDOW_TOPLEVEL);
    gtk_window_set_title(GTK_WINDOW(window), "P2P Chat - GTK");
    gtk_window_set_default_size(GTK_WINDOW(window), 600, 400);

    g_signal_connect(window, "destroy", G_CALLBACK(on_window_destroy), NULL);

    GtkWidget *vbox = gtk_box_new(GTK_ORIENTATION_VERTICAL, 5);
    gtk_container_add(GTK_CONTAINER(window), vbox);

    // صندوق المحادثة
    text_view = gtk_text_view_new();
    gtk_text_view_set_editable(GTK_TEXT_VIEW(text_view), FALSE);
    text_buffer = gtk_text_view_get_buffer(GTK_TEXT_VIEW(text_view));

    GtkWidget *scroll = gtk_scrolled_window_new(NULL, NULL);
    gtk_container_add(GTK_CONTAINER(scroll), text_view);
    gtk_box_pack_start(GTK_BOX(vbox), scroll, TRUE, TRUE, 5);

    // صف IP و Port
    GtkWidget *hbox_conn = gtk_box_new(GTK_ORIENTATION_HORIZONTAL, 5);
    gtk_box_pack_start(GTK_BOX(vbox), hbox_conn, FALSE, FALSE, 5);

    entry_ip = gtk_entry_new();
    gtk_entry_set_placeholder_text(GTK_ENTRY(entry_ip), "IP الطرف الآخر (مثلاً 192.168.1.10)");
    gtk_box_pack_start(GTK_BOX(hbox_conn), entry_ip, TRUE, TRUE, 5);

    entry_port = gtk_entry_new();
    gtk_entry_set_placeholder_text(GTK_ENTRY(entry_port), "المنفذ (مثلاً 5000)");
    gtk_box_pack_start(GTK_BOX(hbox_conn), entry_port, FALSE, FALSE, 5);

    // أزرار الاستماع والاتصال
    GtkWidget *hbox_buttons = gtk_box_new(GTK_ORIENTATION_HORIZONTAL, 5);
    gtk_box_pack_start(GTK_BOX(vbox), hbox_buttons, FALSE, FALSE, 5);

    button_listen = gtk_button_new_with_label("الاستماع كخادم");
    gtk_box_pack_start(GTK_BOX(hbox_buttons), button_listen, TRUE, TRUE, 5);

    button_connect = gtk_button_new_with_label("الاتصال كعميل");
    gtk_box_pack_start(GTK_BOX(hbox_buttons), button_connect, TRUE, TRUE, 5);

    g_signal_connect(button_listen, "clicked", G_CALLBACK(on_listen_clicked), NULL);
    g_signal_connect(button_connect, "clicked", G_CALLBACK(on_connect_clicked), NULL);

    // صف إدخال الرسالة
    GtkWidget *hbox_msg = gtk_box_new(GTK_ORIENTATION_HORIZONTAL, 5);
    gtk_box_pack_start(GTK_BOX(vbox), hbox_msg, FALSE, FALSE, 5);

    entry_message = gtk_entry_new();
    gtk_entry_set_placeholder_text(GTK_ENTRY(entry_message), "اكتب رسالتك هنا...");
    gtk_box_pack_start(GTK_BOX(hbox_msg), entry_message, TRUE, TRUE, 5);

    button_send = gtk_button_new_with_label("إرسال");
    gtk_box_pack_start(GTK_BOX(hbox_msg), button_send, FALSE, FALSE, 5);

    g_signal_connect(button_send, "clicked", G_CALLBACK(on_send_clicked), NULL);

    gtk_widget_show_all(window);
    gtk_main();

    return 0;
}
