import ttkbootstrap as tb
from ttkbootstrap.constants import *
from tkinter import simpledialog, messagebox
import threading
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC


class CourseSelectionGUI:
    def __init__(self, master):
        self.master = master
        master.title("ربات انتخاب واحد")
        master.geometry("600x700")
        master.resizable(True, True)
        style = tb.Style()
        style.theme_use('cyborg')
        style.configure('.', font=('Vazirmatn', 12))

        self.main_frame = tb.Frame(master, bootstyle=DARK)
        self.main_frame.pack(fill=BOTH, expand=True, padx=20, pady=20)

        self.username_label = tb.Label(
            self.main_frame, text="نام کاربری:", bootstyle=DARK, foreground="white", background="#222222")
        self.username_label.grid(row=0, column=0, padx=10, pady=10, sticky=E)
        self.username_entry = tb.Entry(self.main_frame, bootstyle=SECONDARY)
        self.username_entry.grid(row=0, column=1, padx=10, pady=10, sticky=W)

        self.password_label = tb.Label(
            self.main_frame, text="رمز عبور:", bootstyle=DARK, foreground="white", background="#222222")
        self.password_label.grid(row=1, column=0, padx=10, pady=10, sticky=E)
        self.password_entry = tb.Entry(
            self.main_frame, show="*", bootstyle=SECONDARY)
        self.password_entry.grid(row=1, column=1, padx=10, pady=10, sticky=W)

        self.show_password = False

        def toggle_password():
            self.show_password = not self.show_password
            self.password_entry.config(show="" if self.show_password else "*")
            show_btn.config(text="مخفی کن" if self.show_password else "نمایش")
        show_btn = tb.Button(self.main_frame, text="نمایش",
                             bootstyle=SECONDARY, command=toggle_password, width=8)
        show_btn.grid(row=1, column=2, padx=5, pady=10, sticky=W)

        self.num_courses_label = tb.Label(
            self.main_frame, text="تعداد دروس:", bootstyle=DARK, foreground="white", background="#222222")
        self.num_courses_label.grid(
            row=2, column=0, padx=10, pady=10, sticky=E)
        self.num_courses_entry = tb.Entry(self.main_frame, bootstyle=SECONDARY)
        self.num_courses_entry.grid(
            row=2, column=1, padx=10, pady=10, sticky=W)

        self.get_courses_button = tb.Button(
            self.main_frame, text="دریافت اطلاعات دروس", bootstyle=SECONDARY, command=self.get_course_info)
        self.get_courses_button.grid(
            row=3, column=1, padx=10, pady=10, sticky=EW)

        self.start_button = tb.Button(
            self.main_frame, text="شروع", bootstyle=SECONDARY, command=self.start_selection)
        self.start_button.grid(row=4, column=1, padx=10, pady=10, sticky=EW)

        self.warning_message = tb.Label(
            self.main_frame, text="هشدار: لطفاً قبل از رفتن به صفحه ثبت‌نام، دکمه زیر را نزنید!", bootstyle=DARK, foreground="white", background="#222222")
        self.warning_message.grid(
            row=5, column=0, columnspan=2, padx=10, pady=10)

        self.login_message = tb.Label(
            self.main_frame, text="پس از ورود به پورتال، به صفحه ثبت‌نام بروید و سپس دکمه زیر را کلیک کنید:", bootstyle=DARK, foreground="white", background="#222222")
        self.login_message.grid(
            row=6, column=0, columnspan=2, padx=10, pady=10)

        self.continue_button = tb.Button(
            self.main_frame, text="ادامه", bootstyle=SECONDARY, command=self.continue_selection)
        self.continue_button.grid(row=7, column=1, padx=10, pady=10, sticky=EW)

        self.next_priority_button = tb.Button(
            self.main_frame, text="ادامه اولویت بعدی", bootstyle=SECONDARY, command=self.next_priority, state=NORMAL)
        self.next_priority_button.grid(
            row=8, column=1, padx=10, pady=10, sticky=EW)

        for i in range(9):
            self.main_frame.grid_rowconfigure(i, weight=1)
        self.main_frame.grid_columnconfigure(0, weight=1)
        self.main_frame.grid_columnconfigure(1, weight=2)

        self.courses = []
        self.driver = None
        self.current_course_index = 0
        self.course_code_input = None
        self.group_code_input = None
        self.add_button = None

        self.courses_frame = tb.Frame(self.main_frame, bootstyle=DARK)
        self.courses_frame.grid(
            row=9, column=0, columnspan=2, sticky="nsew", padx=5, pady=(10, 0))

        columns = ("name", "code", "group", "priority")
        self.courses_tree = tb.Treeview(
            self.courses_frame, columns=columns, show="headings", height=6, bootstyle=SECONDARY
        )
        self.courses_tree.heading("name", text="نام درس")
        self.courses_tree.heading("code", text="کد درس")
        self.courses_tree.heading("group", text="کد گروه")
        self.courses_tree.heading("priority", text="اولویت")
        self.courses_tree.pack(side="left", fill="both", expand=True)

        scrollbar = tb.Scrollbar(self.courses_frame, orient="vertical",
                                 command=self.courses_tree.yview, bootstyle=SECONDARY)
        self.courses_tree.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side="right", fill="y")

        self.main_frame.grid_rowconfigure(9, weight=2)

        self._add_entry_context_menu(self.username_entry)
        self._add_entry_context_menu(self.password_entry)
        self._add_entry_context_menu(self.num_courses_entry)

    def _add_entry_context_menu(self, entry):
        menu = tb.Menu(entry, tearoff=0)
        menu.add_command(
            label="Paste", command=lambda: entry.event_generate('<<Paste>>'))

        def show_menu(event):
            menu.tk_popup(event.x_root, event.y_root)
        entry.bind("<Button-3>", show_menu)

    def get_course_info(self):
        try:
            num_courses = int(self.num_courses_entry.get())
            self.courses = []
            for i in range(num_courses):
                course_info = self.get_course_details(i + 1)
                if course_info:
                    self.courses.append(course_info)
            self.update_courses_tree()
        except ValueError:
            tb.dialogs.Messagebox.show_error(
                "خطا", "لطفاً یک عدد صحیح برای تعداد دروس وارد کنید.")

    def get_course_details(self, course_number):
        course_window = tb.Toplevel(self.master)
        course_window.title(f"درس {course_number}")
        course_window.geometry("400x220")
        course_window.resizable(True, True)
        frame = tb.Frame(course_window, bootstyle=DARK)
        frame.pack(fill=BOTH, expand=True, padx=10, pady=10)

        name_label = tb.Label(frame, text="نام درس:", bootstyle=DARK,
                              foreground="white", background="#222222")
        name_label.grid(row=0, column=0, padx=5, pady=5, sticky=E)
        name_entry = tb.Entry(frame, bootstyle=SECONDARY)
        name_entry.grid(row=0, column=1, padx=5, pady=5, sticky=W)

        code_label = tb.Label(
            frame, text="کد درس:", bootstyle=DARK, foreground="white", background="#222222")
        code_label.grid(row=1, column=0, padx=5, pady=5, sticky=E)
        code_entry = tb.Entry(frame, bootstyle=SECONDARY)
        code_entry.grid(row=1, column=1, padx=5, pady=5, sticky=W)

        group_label = tb.Label(
            frame, text="کد گروه:", bootstyle=DARK, foreground="white", background="#222222")
        group_label.grid(row=2, column=0, padx=5, pady=5, sticky=E)
        group_entry = tb.Entry(frame, bootstyle=SECONDARY)
        group_entry.grid(row=2, column=1, padx=5, pady=5, sticky=W)

        priority_label = tb.Label(
            frame, text="اولویت (عدد):", bootstyle=DARK, foreground="white", background="#222222")
        priority_label.grid(row=3, column=0, padx=5, pady=5, sticky=E)
        priority_entry = tb.Entry(frame, bootstyle=SECONDARY)
        priority_entry.grid(row=3, column=1, padx=5, pady=5, sticky=W)

        course_info = {}

        def save_course_info():
            course_info["name"] = name_entry.get().strip()
            course_info["code"] = code_entry.get().strip()
            course_info["group"] = group_entry.get().strip()
            try:
                course_info["priority"] = int(priority_entry.get())
            except ValueError:
                tb.dialogs.Messagebox.show_error(
                    "خطا", "لطفاً یک عدد صحیح برای اولویت وارد کنید.")
                return
            course_window.destroy()
        save_button = tb.Button(frame, text="ذخیره",
                                bootstyle=SECONDARY, command=save_course_info)
        save_button.grid(row=4, column=1, padx=5, pady=10, sticky=EW)
        self._add_entry_context_menu(name_entry)
        self._add_entry_context_menu(code_entry)
        self._add_entry_context_menu(group_entry)
        self._add_entry_context_menu(priority_entry)
        course_window.wait_window()
        return course_info if course_info else None

    def update_courses_tree(self):
        for row in self.courses_tree.get_children():
            self.courses_tree.delete(row)
        for course in self.courses:
            self.courses_tree.insert(
                "", "end",
                values=(
                    course.get("name", ""),
                    course.get("code", ""),
                    course.get("group", ""),
                    course.get("priority", "")
                )
            )

    def start_selection(self):
        username = self.username_entry.get()
        password = self.password_entry.get()
        self.current_course_index = 0
        threading.Thread(target=self.login, args=(username, password)).start()

    def login(self, username, password):
        try:
            options = webdriver.ChromeOptions()
            self.driver = webdriver.Chrome(options=options)
            self.driver.get(
                "https://accounts.aut.ac.ir/cas/login?service=https://portal.aut.ac.ir/aportal/ssoGetResponse.jsp")
            username_field = WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located((By.ID, "username"))
            )
            password_field = self.driver.find_element(By.ID, "password")
            username_field.send_keys(username)
            password_field.send_keys(password)
            login_button = WebDriverWait(self.driver, 10).until(
                EC.element_to_be_clickable(
                    (By.XPATH, "//i/input[@type='submit' and @value='ورود']"))
            )
            login_button.click()
            WebDriverWait(self.driver, 20).until(
                EC.presence_of_element_located((By.ID, "logout"))
            )
            # پس از ورود، به صورت خودکار دکمه 'اخذ شده' را در فریم side کلیک کن
            self.go_to_akhd_shodeh()
        except Exception as e:
            print(f"خطا در فرآیند ورود به سیستم: {e}")

    def go_to_akhd_shodeh(self):
        try:
            import time
            # سوییچ به فریم side
            WebDriverWait(self.driver, 10).until(
                EC.frame_to_be_available_and_switch_to_it((By.NAME, "side"))
            )
            # پیدا کردن دکمه/لینک با متن 'اخذ شده'
            links = self.driver.find_elements(By.TAG_NAME, "a")
            for link in links:
                if link.text.strip() == "اخذ شده":
                    link.click()
                    break
            self.driver.switch_to.default_content()
            # کمی صبر کن تا صفحه لود شود
            time.sleep(2)
            # به صورت خودکار یک بار دکمه ادامه اولویت بعدی را بزن
            self.master.after(100, self.next_priority)
        except Exception as e:
            print("خطا در کلیک روی دکمه اخذ شده:", e)

    def continue_selection(self):
        threading.Thread(target=self.analyze_and_prepare).start()

    def analyze_and_prepare(self):
        try:
            if not hasattr(self, 'driver') or self.driver is None:
                return
            self.find_and_store_course_box()
        except Exception as e:
            print(e)

    def find_and_store_course_box(self):
        try:
            self.driver.switch_to.default_content()
            WebDriverWait(self.driver, 10).until(
                EC.frame_to_be_available_and_switch_to_it((By.NAME, "main"))
            )
            inputs = self.driver.find_elements(
                By.XPATH, "//input[@type='text']")
            button = self.driver.find_element(
                By.XPATH, "//input[@type='submit' and @name='st_course_add']")
            self.course_code_input = inputs[0]
            self.group_code_input = inputs[1]
            self.add_button = button
        except Exception as e:
            print("خطا در پیدا کردن باکس اخذ واحد:", e)

    def next_priority(self):
        threading.Thread(target=self.fill_course_fields).start()

    def fill_course_fields(self):
        try:
            if not hasattr(self, 'current_course_index'):
                self.current_course_index = 0
            # sort by priority (lowest number = highest priority)
            sorted_courses = sorted(
                self.courses, key=lambda x: x.get("priority", 0))
            if self.current_course_index >= len(sorted_courses):
                return
            course = sorted_courses[self.current_course_index]
            self.course_code_input.clear()
            self.course_code_input.send_keys(course["code"])
            self.group_code_input.clear()
            self.group_code_input.send_keys(course["group"])
            self.current_course_index += 1
        except Exception as e:
            print("خطا در پر کردن ورودی‌ها:", e)


if __name__ == "__main__":
    root = tb.Window(themename="cyborg")
    gui = CourseSelectionGUI(root)
    root.mainloop()
