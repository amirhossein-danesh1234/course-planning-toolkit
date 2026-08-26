import ttkbootstrap as tb
from ttkbootstrap.constants import *
from tkinter import simpledialog, messagebox
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import threading


class CourseSelectionGUI:
    def __init__(self, master):
        self.master = master
        master.title("ربات انتخاب واحد")
        master.geometry("480x500")
        master.resizable(False, False)
        style = tb.Style()
        style.theme_use('cyborg')  # دارک مود
        style.configure('.', font=('Vazirmatn', 12))  # اگر فونت نصب است

        # قاب اصلی
        self.main_frame = tb.Frame(master, bootstyle=DARK)
        self.main_frame.pack(fill=BOTH, expand=True, padx=20, pady=20)

        # برچسب و فیلد نام کاربری
        self.username_label = tb.Label(
            self.main_frame, text="نام کاربری:", bootstyle=DARK, foreground="white", background="#222222")
        self.username_label.grid(row=0, column=0, padx=10, pady=10, sticky=E)
        self.username_entry = tb.Entry(self.main_frame, bootstyle=SECONDARY)
        self.username_entry.grid(row=0, column=1, padx=10, pady=10, sticky=W)

        # برچسب و فیلد رمز عبور
        self.password_label = tb.Label(
            self.main_frame, text="رمز عبور:", bootstyle=DARK, foreground="white", background="#222222")
        self.password_label.grid(row=1, column=0, padx=10, pady=10, sticky=E)
        self.password_entry = tb.Entry(
            self.main_frame, show="*", bootstyle=SECONDARY)
        self.password_entry.grid(row=1, column=1, padx=10, pady=10, sticky=W)

        # برچسب و فیلد تعداد دروس
        self.num_courses_label = tb.Label(
            self.main_frame, text="تعداد دروس:", bootstyle=DARK, foreground="white", background="#222222")
        self.num_courses_label.grid(
            row=2, column=0, padx=10, pady=10, sticky=E)
        self.num_courses_entry = tb.Entry(self.main_frame, bootstyle=SECONDARY)
        self.num_courses_entry.grid(
            row=2, column=1, padx=10, pady=10, sticky=W)

        # دکمه دریافت اطلاعات دروس
        self.get_courses_button = tb.Button(
            self.main_frame, text="دریافت اطلاعات دروس", bootstyle=SECONDARY, command=self.get_course_info)
        self.get_courses_button.grid(
            row=3, column=1, padx=10, pady=10, sticky=EW)

        # دکمه شروع
        self.start_button = tb.Button(
            self.main_frame, text="شروع", bootstyle=SECONDARY, command=self.start_selection)
        self.start_button.grid(row=4, column=1, padx=10, pady=10, sticky=EW)

        # پیام هشدار به کاربر (فقط رنگ نوشته سفید)
        self.warning_message = tb.Label(
            self.main_frame, text="هشدار: لطفاً قبل از رفتن به صفحه ثبت‌نام، دکمه زیر را نزنید!", bootstyle=DARK, foreground="white", background="#222222")
        self.warning_message.grid(
            row=5, column=0, columnspan=2, padx=10, pady=10)

        # پیام به کاربر
        self.login_message = tb.Label(
            self.main_frame, text="پس از ورود به پورتال، به صفحه ثبت‌نام بروید و سپس دکمه زیر را کلیک کنید:", bootstyle=DARK, foreground="white", background="#222222")
        self.login_message.grid(
            row=6, column=0, columnspan=2, padx=10, pady=10)

        # دکمه "ادامه"
        self.continue_button = tb.Button(
            self.main_frame, text="ادامه", bootstyle=SECONDARY, command=self.continue_selection)
        self.continue_button.grid(row=7, column=1, padx=10, pady=10, sticky=EW)

        # دکمه "ادامه اولویت بعدی"
        self.next_priority_button = tb.Button(
            self.main_frame, text="ادامه اولویت بعدی", bootstyle=SECONDARY, command=self.next_priority, state=DISABLED)
        self.next_priority_button.grid(
            row=8, column=1, padx=10, pady=10, sticky=EW)

        # زیباسازی بیشتر
        for i in range(9):
            self.main_frame.grid_rowconfigure(i, weight=1)
        self.main_frame.grid_columnconfigure(0, weight=1)
        self.main_frame.grid_columnconfigure(1, weight=2)

        self.courses = []
        self.driver = None
        self.logged_in = False
        self.current_priority_index = 0

    def get_course_info(self):
        try:
            num_courses = int(self.num_courses_entry.get())
            self.courses = []
            for i in range(num_courses):
                course_info = self.get_course_details(i + 1)
                if course_info:
                    self.courses.append(course_info)
        except ValueError:
            tb.dialogs.Messagebox.show_error(
                "خطا", "لطفاً یک عدد صحیح برای تعداد دروس وارد کنید.")

    def get_course_details(self, course_number):
        course_window = tb.Toplevel(self.master)
        course_window.title(f"درس {course_number}")
        course_window.geometry("350x150")
        course_window.resizable(False, False)
        frame = tb.Frame(course_window, bootstyle=DARK)
        frame.pack(fill=BOTH, expand=True, padx=10, pady=10)

        section_label = tb.Label(
            frame, text="انتخاب بخش:", bootstyle=DARK, foreground="white", background="#222222")
        section_label.grid(row=0, column=0, padx=5, pady=5, sticky=E)
        section_choices = ["بسته آموزشی", "دانشکده", "ریاضیات", "فیزیک", "آز فیزیک 1", "آز فیزیک 2", "سرویس", "زبان",
                           "تاریخ اسلام", "اندیشه اسلامی", "فارسی", "اخلاق اسلامی", "انقلاب", "تفسیر موضوعی", "خانواده", "تربیت بدنی"]
        section_combobox = tb.Combobox(
            frame, values=section_choices, state="readonly", bootstyle=SECONDARY)
        section_combobox.grid(row=0, column=1, padx=5, pady=5, sticky=W)

        priority_label = tb.Label(
            frame, text="اولویت (عدد):", bootstyle=DARK, foreground="white", background="#222222")
        priority_label.grid(row=1, column=0, padx=5, pady=5, sticky=E)
        priority_entry = tb.Entry(frame, bootstyle=SECONDARY)
        priority_entry.grid(row=1, column=1, padx=5, pady=5, sticky=W)

        course_info = {}

        def save_course_info():
            course_info["section"] = section_combobox.get()
            try:
                course_info["priority"] = int(priority_entry.get())
            except ValueError:
                tb.dialogs.Messagebox.show_error(
                    "خطا", "لطفاً یک عدد صحیح برای اولویت وارد کنید.")
                return
            course_window.destroy()
        save_button = tb.Button(frame, text="ذخیره",
                                bootstyle=SECONDARY, command=save_course_info)
        save_button.grid(row=2, column=1, padx=5, pady=10, sticky=EW)
        course_window.wait_window()
        return course_info if course_info else None

    def start_selection(self):
        username = self.username_entry.get()
        password = self.password_entry.get()
        self.current_priority_index = 0
        threading.Thread(target=self.login, args=(username, password)).start()

    def continue_selection(self):
        self.next_priority_button.config(state=NORMAL)

    def next_priority(self):
        threading.Thread(target=self.select_course_by_priority).start()

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
            try:
                WebDriverWait(self.driver, 20).until(
                    EC.presence_of_element_located((By.ID, "logout"))
                )
            except Exception as e:
                tb.dialogs.Messagebox.show_error(
                    "خطا", f"خطا در ورود به سیستم: {e}")
                return
            self.logged_in = True
        except Exception as e:
            tb.dialogs.Messagebox.show_error(
                "خطا", f"خطا در فرآیند ورود به سیستم: {e}")

    def select_course_by_priority(self):
        try:
            if self.driver:
                sorted_courses = sorted(
                    self.courses, key=lambda x: x["priority"])
                if self.current_priority_index < len(sorted_courses):
                    course = sorted_courses[self.current_priority_index]
                    self.open_section(self.driver, course["section"])
                    self.current_priority_index += 1
                else:
                    tb.dialogs.Messagebox.show_info(
                        "پیام", "تمام اولویت‌ها بررسی شدند.")
                    self.driver.quit()
        except Exception as e:
            tb.dialogs.Messagebox.show_error(
                "خطا", f"خطا در فرآیند انتخاب دروس بر اساس اولویت: {e}")

    def open_section(self, driver, section_name):
        try:
            right_panel = WebDriverWait(driver, 10).until(
                EC.presence_of_element_located(
                    (By.XPATH, "//frame[@name='side']"))
            )
            driver.switch_to.frame(right_panel)
            section_id_map = {
                "بسته آموزشی": "Bar_panel1_b1",
                "دانشکده": "Bar_panel1_b2",
                "ریاضیات": "Bar_panel1_b3",
                "فیزیک": "Bar_panel1_b4",
                "آز فیزیک 1": "Bar_panel1_b5",
                "آز فیزیک 2": "Bar_panel1_b6",
                "سرویس": "Bar_panel1_b7",
                "زبان": "Bar_panel1_b8",
                "تاریخ اسلام": "Bar_panel1_b9",
                "اندیشه اسلامی": "Bar_panel1_b10",
                "فارسی": "Bar_panel1_b11",
                "اخلاق اسلامی": "Bar_panel1_b12",
                "انقلاب": "Bar_panel1_b13",
                "تفسیر موضوعی": "Bar_panel1_b14",
                "خانواده": "Bar_panel1_b15",
                "تربیت بدنی": "Bar_panel1_b16"
            }
            section_id = section_id_map[section_name]
            section_element = WebDriverWait(driver, 10).until(
                EC.element_to_be_clickable(
                    (By.XPATH, f"//div[@id='{section_id}']/a"))
            )
            section_element.click()
            driver.switch_to.default_content()
        except Exception as e:
            tb.dialogs.Messagebox.show_error(
                "خطا", f"خطا در باز کردن بخش {section_name}: {e}")


if __name__ == "__main__":
    root = tb.Window(themename="cyborg")  # دارک مود
    gui = CourseSelectionGUI(root)
    root.mainloop()
