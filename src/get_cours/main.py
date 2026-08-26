from __future__ import annotations

import re
import time
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from typing import Callable, Dict, List, Tuple

import pandas as pd
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.common.exceptions import WebDriverException
from selenium.webdriver.chrome.options import Options as ChromeOptions
from selenium.webdriver.common.by import By
from selenium.webdriver.edge.options import Options as EdgeOptions


FIELD_DEFINITIONS = [
    ("course_number", "شماره درس"),
    ("course_name", "نام درس"),
    ("course_group", "گروه درس"),
    ("theory_practical_units", "واحد تئوری/عملی"),
    ("capacity_registered_waiting", "ظرفیت-ثبت نام شده-لیست انتظار"),
    ("instructor", "مدرس"),
    ("time_location", "زمان/مکان ارائه"),
    ("class_time_1", "تایم اول"),
    ("class_time_2", "تایم دوم"),
    ("class_location", "محل برگزاری کلاس"),
    ("exam_day", "روز امتحان"),
    ("exam_time", "زمان امتحان"),
    ("prerequisite", "پیشنیاز"),
    ("corequisite", "همنیاز"),
    ("conflict", "متضاد"),
    ("course_allowed_system", "نظام مجاز به اخذ درس"),
    ("group_allowed_system", "نظام مجاز به اخذ گروه"),
]
FIELD_LABELS = dict(FIELD_DEFINITIONS)

PERSIAN_DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹", "0123456789")
ARABIC_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789")
DAY_NORMALIZATION = {
    "شنبه": "شنبه",
    "یکشنبه": "یکشنبه",
    "یک شنبه": "یکشنبه",
    "يكشنبه": "یکشنبه",
    "يك شنبه": "یکشنبه",
    "دوشنبه": "دوشنبه",
    "سه شنبه": "سه شنبه",
    "سه‌شنبه": "سه شنبه",
    "سهشنبه": "سه شنبه",
    "چهارشنبه": "چهارشنبه",
    "پنجشنبه": "پنجشنبه",
    "جمعه": "جمعه",
}
DAY_PATTERN_PART = "|".join(sorted((re.escape(k) for k in DAY_NORMALIZATION), key=len, reverse=True))
DAY_TOKEN_PATTERN = re.compile(rf"(?P<day>{DAY_PATTERN_PART})")
TIME_RANGE_PATTERN = re.compile(r"(?P<start>\d{1,2}[:٫]\d{2})\s*[-–]\s*(?P<end>\d{1,2}[:٫]\d{2})")
DAY_TIME_WITH_OPTIONAL_KIND_PATTERN = re.compile(
    rf"(?P<day>{DAY_PATTERN_PART})\s*(?:عملی|عملي)?\s*"
    r"(?P<start>\d{1,2}[:٫]\d{2})\s*[-–]\s*(?P<end>\d{1,2}[:٫]\d{2})"
)


def normalize_text(value: str) -> str:
    text = (value or "").translate(PERSIAN_DIGITS).translate(ARABIC_DIGITS)
    text = (
        text.replace("\u200c", " ")
        .replace("ي", "ی")
        .replace("ك", "ک")
        .replace("ۀ", "ه")
    )
    return re.sub(r"\s+", " ", text).strip()


def normalize_day_name(day_name: str) -> str:
    return DAY_NORMALIZATION.get(normalize_text(day_name), "")


def normalize_hhmm(value: str) -> str:
    text = normalize_text(value).replace("٫", ":")
    match = re.fullmatch(r"(\d{1,2}):(\d{2})", text)
    if not match:
        return ""
    hour = int(match.group(1))
    minute = int(match.group(2))
    if hour < 0 or hour > 23 or minute < 0 or minute > 59:
        return ""
    return f"{hour:02d}:{minute:02d}"


def parse_class_time_slots(time_location_text: str) -> List[Tuple[str, str, str]]:
    text = normalize_text(time_location_text)
    if not text:
        return []

    day_positions: List[Tuple[int, str]] = []
    for day_match in DAY_TOKEN_PATTERN.finditer(text):
        day_name = normalize_day_name(day_match.group("day"))
        if day_name:
            day_positions.append((day_match.start(), day_name))

    slots: List[Tuple[str, str, str]] = []
    seen = set()
    for time_match in TIME_RANGE_PATTERN.finditer(text):
        day = ""
        for pos, day_name in day_positions:
            if pos <= time_match.start():
                day = day_name
            else:
                break
        if not day and day_positions:
            day = day_positions[0][1]

        start = normalize_hhmm(time_match.group("start"))
        end = normalize_hhmm(time_match.group("end"))
        if not day or not start or not end:
            continue

        key = (day, start, end)
        if key in seen:
            continue
        seen.add(key)
        slots.append(key)

    return slots


def format_class_time_slots(slots: List[Tuple[str, str, str]]) -> str:
    return " | ".join(f"{day} {start}-{end}" for day, start, end in slots)


def format_single_slot(slot: Tuple[str, str, str]) -> str:
    day, start, end = slot
    return f"{day} {start}-{end}"


def split_first_two_times(slots: List[Tuple[str, str, str]]) -> Tuple[str, str]:
    time_1 = format_single_slot(slots[0]) if len(slots) >= 1 else ""
    time_2 = format_single_slot(slots[1]) if len(slots) >= 2 else ""
    return time_1, time_2


def _clean_location_text(value: str) -> str:
    text = normalize_text(value)
    if not text:
        return ""
    text = DAY_TOKEN_PATTERN.sub(" ", text)
    text = TIME_RANGE_PATTERN.sub(" ", text)
    text = re.sub(r"\b(?:عملی|عملي)\b", " ", text)
    text = re.sub(r"[|،,;؛]+", " ", text)
    return normalize_text(text)


def extract_class_location(time_location_text: str) -> str:
    text = normalize_text(time_location_text)
    if not text:
        return ""

    matches = list(DAY_TIME_WITH_OPTIONAL_KIND_PATTERN.finditer(text))
    location_chunks: List[str] = []

    if matches:
        prev_end = matches[0].end()
        for i in range(1, len(matches)):
            between = _clean_location_text(text[prev_end:matches[i].start()])
            if between:
                location_chunks.append(between)
            prev_end = matches[i].end()

        tail = _clean_location_text(text[prev_end:])
        if tail:
            location_chunks.append(tail)
    else:
        cleaned = _clean_location_text(text)
        if cleaned:
            location_chunks.append(cleaned)

    unique_locations: List[str] = []
    seen = set()
    for chunk in location_chunks:
        if chunk and chunk not in seen:
            unique_locations.append(chunk)
            seen.add(chunk)

    return " | ".join(unique_locations)


def element_text(node) -> str:
    if node is None:
        return ""
    return normalize_text(node.get_text(" ", strip=True))


def list_text_from_group(root, bind_fragment: str) -> str:
    node = root.select_one(f'div.groupInput[data-bind*="{bind_fragment}"]')
    if node is None:
        return ""

    values = []
    for child in node.find_all("div", recursive=False):
        text = element_text(child)
        if text:
            values.append(text)

    if not values:
        values = [normalize_text(s) for s in node.stripped_strings if normalize_text(s)]

    unique_values = []
    seen = set()
    for value in values:
        if value not in seen:
            unique_values.append(value)
            seen.add(value)

    return " | ".join(unique_values)


class CourseExtractor:
    CONDITION_FIELDS = {
        "prerequisite",
        "corequisite",
        "conflict",
        "course_allowed_system",
        "group_allowed_system",
    }

    def __init__(
        self,
        driver: webdriver.Remote,
        status_callback: Callable[[str], None],
        selected_fields: List[str] | None = None,
    ) -> None:
        self.driver = driver
        self.status_callback = status_callback
        self.selected_fields = set(selected_fields or [])

    def extract(self) -> List[Dict[str, str]]:
        self._wait_for_panels_stable()
        if self._needs_condition_loading():
            self._load_hidden_conditions()
            self._wait_for_panels_stable()
        html = self.driver.page_source
        return self._parse_html(html)

    def _needs_condition_loading(self) -> bool:
        if not self.selected_fields:
            return True
        return bool(self.CONDITION_FIELDS & self.selected_fields)

    def _load_hidden_conditions(self) -> None:
        self.status_callback("در حال بارگذاری پیش‌نیاز/هم‌نیاز/نظام‌های مجاز...")
        selector = (
            'a.np-hyperlink.d-block[data-bind*="_V_CrsCond"], '
            'a.np-hyperlink.d-block[data-bind*="_V_GrpCond"]'
        )
        click_delay = 1.6
        batch_pause = 5.0

        links = self.driver.find_elements(By.CSS_SELECTOR, selector)
        total = len(links)
        if total == 0:
            return

        self.status_callback(f"در حال بارگذاری شروط ({total} مورد)...")
        for index in range(total):
            try:
                refreshed = self.driver.find_elements(By.CSS_SELECTOR, selector)
                if index >= len(refreshed):
                    break
                link = refreshed[index]
                self.driver.execute_script("arguments[0].scrollIntoView({block:'center'});", link)
                self.driver.execute_script("arguments[0].click();", link)
                time.sleep(click_delay)
                if index > 0 and index % 6 == 0:
                    time.sleep(batch_pause)
            except Exception:
                continue

        time.sleep(4.0)

    def _wait_for_panels_stable(self) -> None:
        script = "return document.querySelectorAll('div.collapse[id]').length;"
        stable_hits = 0
        last_count = -1
        for _ in range(24):
            try:
                count = int(self.driver.execute_script(script))
            except Exception:
                time.sleep(0.6)
                continue
            if count > 0 and count == last_count:
                stable_hits += 1
            else:
                stable_hits = 0
            last_count = count
            if stable_hits >= 3:
                break
            time.sleep(0.6)

    def _parse_html(self, html: str) -> List[Dict[str, str]]:
        self.status_callback("در حال خواندن داده‌ها از صفحه...")
        soup = BeautifulSoup(html, "html.parser")
        panels = soup.select("div.collapse[id]")

        rows: List[Dict[str, str]] = []
        seen_keys = set()

        for panel in panels:
            course_number = element_text(panel.select_one('div.groupInput[data-bind*="$parent.ln"]'))
            course_group = element_text(panel.select_one('div.part[data-bind*="text:g"]'))
            if not course_number or not course_group:
                continue

            key = (course_number, course_group)
            if key in seen_keys:
                continue
            seen_keys.add(key)

            course_name = element_text(panel.select_one('div.groupInput[data-bind*="$parent.n"]'))
            theory = element_text(panel.select_one('div.part[data-bind*="$parent.tu"]'))
            practical = element_text(panel.select_one('div.part[data-bind*="$parent.lu"]'))
            capacity = element_text(panel.select_one('div.part[data-bind*="text:dc"]'))
            registered = element_text(panel.select_one('div.part[data-bind*="text:rc"]'))
            waiting = element_text(panel.select_one('div.part[data-bind*="text:wc"]'))

            teacher_block = panel.select_one('div.groupInput[data-bind*="foreach:$data.tch"]')
            instructor = element_text(teacher_block)

            time_block = panel.select_one('div.groupInput[data-bind*="_V_NoEmptyItem($data.time)"]')
            time_location = element_text(time_block)
            parsed_slots = parse_class_time_slots(time_location)
            class_time_1, class_time_2 = split_first_two_times(parsed_slots)
            class_location = extract_class_location(time_location)

            exam_day = element_text(panel.select_one('div.groupInput[data-bind*="$data.exm.ed"]'))
            exam_time = element_text(panel.select_one('div.groupInput[data-bind*="$data.exm.et"]'))

            row = {
                "course_number": course_number,
                "course_name": course_name,
                "course_group": course_group,
                "theory_practical_units": f"{theory}/{practical}" if theory or practical else "",
                "capacity_registered_waiting": (
                    f"{capacity}-{registered}-{waiting}" if capacity or registered or waiting else ""
                ),
                "instructor": instructor,
                "time_location": time_location,
                "class_time_1": class_time_1,
                "class_time_2": class_time_2,
                "class_location": class_location,
                "exam_day": exam_day,
                "exam_time": exam_time,
                "prerequisite": list_text_from_group(panel, "foreach:$parent.cond().pre"),
                "corequisite": list_text_from_group(panel, "foreach:$parent.cond().cor"),
                "conflict": list_text_from_group(panel, "foreach:$parent.cond().cont"),
                "course_allowed_system": list_text_from_group(panel, "foreach:$parent.cond().perm"),
                "group_allowed_system": list_text_from_group(panel, "foreach:$data.condtrm().permtrm"),
            }
            rows.append(row)

        return rows


class CourseApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("استخراج اطلاعات دروس")
        self.geometry("980x700")
        self.minsize(860, 620)

        self.driver: webdriver.Remote | None = None
        self.field_vars: Dict[str, tk.BooleanVar] = {}

        self.url_var = tk.StringVar(value="portal.aut.ac.ir")
        self.status_var = tk.StringVar(value="آماده")

        self._build_ui()
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    def _build_ui(self) -> None:
        top_frame = ttk.Frame(self, padding=12)
        top_frame.pack(fill=tk.X)

        ttk.Label(top_frame, text="آدرس وب‌سایت:").pack(side=tk.RIGHT, padx=(8, 0))
        ttk.Entry(top_frame, textvariable=self.url_var, width=60, justify="left").pack(
            side=tk.RIGHT, fill=tk.X, expand=True
        )

        self.open_btn = ttk.Button(top_frame, text="باز کردن وب", command=self.open_website)
        self.open_btn.pack(side=tk.LEFT, padx=(0, 8))

        checks_frame = ttk.LabelFrame(self, text="فیلدهای خروجی", padding=12)
        checks_frame.pack(fill=tk.BOTH, expand=True, padx=12, pady=(0, 12))

        for idx, (field_key, label) in enumerate(FIELD_DEFINITIONS):
            var = tk.BooleanVar(value=True)
            self.field_vars[field_key] = var
            row = idx // 2
            col = idx % 2
            ttk.Checkbutton(checks_frame, text=label, variable=var).grid(
                row=row, column=col, sticky="w", padx=10, pady=6
            )

        checks_frame.columnconfigure(0, weight=1)
        checks_frame.columnconfigure(1, weight=1)

        self.extract_btn = ttk.Button(self, text="استخراج اطلاعات", command=self.extract_data)
        self.extract_btn.pack(pady=(0, 10))

        ttk.Label(self, textvariable=self.status_var, anchor="e").pack(fill=tk.X, padx=12, pady=(0, 12))

    def set_status(self, message: str) -> None:
        self.status_var.set(message)
        self.update_idletasks()

    def open_website(self) -> None:
        try:
            if self.driver is None:
                self.driver = self._create_driver()
            url = normalize_text(self.url_var.get()) or "about:blank"
            if url != "about:blank" and not re.match(r"^https?://", url, flags=re.IGNORECASE):
                url = f"https://{url}"
            self.driver.get(url)
            self.set_status("مرورگر باز شد. وارد مسیر انتخاب واحد شوید.")
        except Exception as exc:
            messagebox.showerror("خطا", f"باز کردن مرورگر انجام نشد:\n{exc}")
            self.set_status("خطا در باز کردن مرورگر")

    def extract_data(self) -> None:
        if self.driver is None:
            messagebox.showwarning("مرورگر بسته است", "ابتدا روی «باز کردن وب» بزنید.")
            return

        selected_fields = [key for key, var in self.field_vars.items() if var.get()]
        if not selected_fields:
            messagebox.showwarning("فیلد انتخاب نشده", "حداقل یک فیلد را انتخاب کنید.")
            return

        try:
            self.extract_btn.config(state=tk.DISABLED)
            self.set_status("در حال استخراج اطلاعات...")
            extractor = CourseExtractor(self.driver, self.set_status, selected_fields)
            records = extractor.extract()
        except Exception as exc:
            messagebox.showerror("خطا", f"استخراج اطلاعات انجام نشد:\n{exc}")
            self.set_status("خطا در استخراج")
            return
        finally:
            self.extract_btn.config(state=tk.NORMAL)

        if not records:
            messagebox.showinfo("بدون داده", "هیچ رکورد درسی پیدا نشد.")
            self.set_status("رکوردی پیدا نشد")
            return

        self.set_status(f"{len(records)} رکورد استخراج شد")
        self._show_results_window(records, selected_fields)

    def _show_results_window(self, records: List[Dict[str, str]], selected_fields: List[str]) -> None:
        window = tk.Toplevel(self)
        window.title("نتایج استخراج")
        window.geometry("1200x650")

        tree_frame = ttk.Frame(window, padding=10)
        tree_frame.pack(fill=tk.BOTH, expand=True)

        columns = selected_fields
        tree = ttk.Treeview(tree_frame, columns=columns, show="headings")

        for field in columns:
            tree.heading(field, text=FIELD_LABELS[field])
            tree.column(field, width=160, anchor="center")

        y_scroll = ttk.Scrollbar(tree_frame, orient=tk.VERTICAL, command=tree.yview)
        x_scroll = ttk.Scrollbar(tree_frame, orient=tk.HORIZONTAL, command=tree.xview)
        tree.configure(yscrollcommand=y_scroll.set, xscrollcommand=x_scroll.set)

        tree.grid(row=0, column=0, sticky="nsew")
        y_scroll.grid(row=0, column=1, sticky="ns")
        x_scroll.grid(row=1, column=0, sticky="ew")

        tree_frame.rowconfigure(0, weight=1)
        tree_frame.columnconfigure(0, weight=1)

        for record in records:
            row = [record.get(field, "") for field in columns]
            tree.insert("", tk.END, values=row)

        btn_frame = ttk.Frame(window, padding=(10, 0, 10, 10))
        btn_frame.pack(fill=tk.X)

        ttk.Button(
            btn_frame,
            text="دریافت فایل Excel",
            command=lambda: self._export_excel(records, selected_fields),
        ).pack(side=tk.LEFT)

        ttk.Label(btn_frame, text=f"تعداد رکورد: {len(records)}").pack(side=tk.RIGHT)

    def _export_excel(self, records: List[Dict[str, str]], selected_fields: List[str]) -> None:
        path = filedialog.asksaveasfilename(
            title="ذخیره فایل خروجی",
            defaultextension=".xlsx",
            filetypes=[("Excel", "*.xlsx"), ("All Files", "*.*")],
        )
        if not path:
            return

        try:
            data = [
                {FIELD_LABELS[field]: record.get(field, "") for field in selected_fields}
                for record in records
            ]
            df = pd.DataFrame(data)
            df.to_excel(path, index=False)
            messagebox.showinfo("موفق", "فایل خروجی با موفقیت ذخیره شد.")
        except Exception as exc:
            messagebox.showerror("خطا", f"ذخیره فایل انجام نشد:\n{exc}")

    @staticmethod
    def _create_driver() -> webdriver.Remote:
        chrome_options = ChromeOptions()
        chrome_options.add_argument("--start-maximized")

        try:
            return webdriver.Chrome(options=chrome_options)
        except WebDriverException:
            edge_options = EdgeOptions()
            edge_options.add_argument("--start-maximized")
            return webdriver.Edge(options=edge_options)

    def _on_close(self) -> None:
        if self.driver is not None:
            try:
                self.driver.quit()
            except Exception:
                pass
        self.destroy()


def main() -> None:
    app = CourseApp()
    app.mainloop()


if __name__ == "__main__":
    main()
