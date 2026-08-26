from __future__ import annotations

import math
import re
import tkinter as tk
from dataclasses import dataclass
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import Dict, List, Optional, Sequence, Tuple

import pandas as pd


DAY_ORDER = ["شنبه", "یکشنبه", "دوشنبه", "سه شنبه", "چهارشنبه", "پنجشنبه", "جمعه"]
PERSIAN_DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹", "0123456789")
ARABIC_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789")
DAY_ALIASES = {
    "شنبه": "شنبه",
    "یکشنبه": "یکشنبه",
    "يكشنبه": "یکشنبه",
    "دوشنبه": "دوشنبه",
    "سه شنبه": "سه شنبه",
    "سه‌شنبه": "سه شنبه",
    "سهشنبه": "سه شنبه",
    "چهارشنبه": "چهارشنبه",
    "پنجشنبه": "پنجشنبه",
    "جمعه": "جمعه",
}
DAY_PATTERN = re.compile(r"(شنبه|یکشنبه|يكشنبه|دوشنبه|سه شنبه|سه‌شنبه|سهشنبه|چهارشنبه|پنجشنبه|جمعه)")
TIME_PATTERN = re.compile(r"(\d{1,2}:\d{2})\s*[-–]\s*(\d{1,2}:\d{2})")

COLUMN_ALIASES = {
    "course_number": ("شماره درس", "course_number"),
    "course_name": ("نام درس", "course_name"),
    "course_group": ("گروه درس", "course_group"),
    "capacity_registered_waiting": ("ظرفیت-ثبت نام شده-لیست انتظار", "capacity_registered_waiting"),
    "instructor": ("مدرس", "instructor"),
    "time_location": ("زمان/مکان ارائه", "time_location"),
    "class_time_slots": (
        "بازه‌های زمانی کلاس (استخراج‌شده)",
        "بازه های زمانی کلاس (استخراج شده)",
        "class_time_slots",
    ),
    "class_time_1": ("تایم اول", "class_time_1"),
    "class_time_2": ("تایم دوم", "class_time_2"),
    "class_location": ("محل برگزاری کلاس", "class_location"),
    "exam_day": ("روز امتحان", "exam_day"),
    "exam_time": ("زمان امتحان", "exam_time"),
    "units": ("واحد تئوری/عملی", "theory_practical_units"),
}


@dataclass(frozen=True)
class TimeSlot:
    day: str
    start_min: int
    end_min: int


@dataclass(frozen=True)
class ExamSlot:
    day: str
    start_min: int
    end_min: int


@dataclass
class CourseOffer:
    course_number: str
    course_name: str
    course_group: str
    instructor: str
    time_location: str
    exam_day: str
    exam_time: str
    class_time_1: str
    class_time_2: str
    class_location: str
    units_text: str
    unit_value: float
    capacity_registered_waiting: str
    class_slots: List[TimeSlot]
    exam_slot: Optional[ExamSlot]
    is_full: bool
    instructor_tokens: List[str]


def normalize_text(value: object) -> str:
    text = "" if value is None else str(value)
    text = text.translate(PERSIAN_DIGITS).translate(ARABIC_DIGITS)
    text = (
        text.replace("\u200c", " ")
        .replace("‌", " ")
        .replace("ي", "ی")
        .replace("ك", "ک")
        .replace("ۀ", "ه")
    )
    return re.sub(r"\s+", " ", text).strip()


def parse_hhmm(time_str: str) -> Optional[int]:
    p = time_str.split(":")
    if len(p) != 2:
        return None
    try:
        h, m = int(p[0]), int(p[1])
    except ValueError:
        return None
    if not (0 <= h <= 23 and 0 <= m <= 59):
        return None
    return h * 60 + m


def minutes_to_hhmm(v: int) -> str:
    return f"{v // 60:02d}:{v % 60:02d}"


def format_slots(slots: Sequence[TimeSlot]) -> str:
    return " | ".join(f"{s.day} {minutes_to_hhmm(s.start_min)}-{minutes_to_hhmm(s.end_min)}" for s in slots)


def format_slot(slot: TimeSlot) -> str:
    return f"{slot.day} {minutes_to_hhmm(slot.start_min)}-{minutes_to_hhmm(slot.end_min)}"


def parse_single_slot_text(slot_text: str) -> Optional[TimeSlot]:
    text = normalize_text(slot_text)
    if not text:
        return None
    day_match = DAY_PATTERN.search(text)
    time_match = TIME_PATTERN.search(text)
    if not day_match or not time_match:
        return None
    day = DAY_ALIASES.get(normalize_text(day_match.group(1)))
    s, e = parse_hhmm(time_match.group(1)), parse_hhmm(time_match.group(2))
    if not day or s is None or e is None or e <= s:
        return None
    return TimeSlot(day=day, start_min=s, end_min=e)


def overlap(a1: int, a2: int, b1: int, b2: int) -> bool:
    return a1 < b2 and b1 < a2


def split_instructor_names(value: str) -> List[str]:
    text = normalize_text(value)
    if not text:
        return []
    parts = [normalize_text(x) for x in re.split(r"[|/,،]+", text)]
    out, seen = [], set()
    for p in parts:
        if p and p not in seen:
            out.append(p)
            seen.add(p)
    return out


def parse_capacity_full(capacity_text: str) -> bool:
    nums = re.findall(r"\d+", normalize_text(capacity_text))
    if len(nums) < 2:
        return False
    cap, reg = int(nums[0]), int(nums[1])
    return cap > 0 and reg >= cap


def parse_units_total(units_text: str) -> float:
    text = normalize_text(units_text)
    if not text:
        return 0.0
    nums = re.findall(r"\d+(?:\.\d+)?", text)
    if not nums:
        return 0.0
    vals = [float(n) for n in nums]
    if "/" in text and len(vals) >= 2:
        return vals[0] + vals[1]
    if len(vals) >= 2:
        return vals[0] + vals[1]
    return vals[0]


def normalize_day(v: str) -> Optional[str]:
    return DAY_ALIASES.get(normalize_text(v))


def parse_class_slots(time_location_text: str) -> List[TimeSlot]:
    text = normalize_text(time_location_text)
    if not text:
        return []

    day_positions: List[Tuple[int, str]] = []
    for m in DAY_PATTERN.finditer(text):
        day = DAY_ALIASES.get(normalize_text(m.group(1)))
        if day:
            day_positions.append((m.start(), day))

    seen, out = set(), []
    for t in TIME_PATTERN.finditer(text):
        s, e = parse_hhmm(t.group(1)), parse_hhmm(t.group(2))
        if s is None or e is None or e <= s:
            continue
        day = None
        for pos, d in day_positions:
            if pos <= t.start():
                day = d
            else:
                break
        if day is None and day_positions:
            day = day_positions[0][1]
        if day is None:
            continue
        key = (day, s, e)
        if key in seen:
            continue
        seen.add(key)
        out.append(TimeSlot(day=day, start_min=s, end_min=e))
    return out


def parse_class_slots_compact(class_slots_text: str) -> List[TimeSlot]:
    text = normalize_text(class_slots_text)
    if not text:
        return []

    parts = [normalize_text(p) for p in re.split(r"[|؛;]+", text) if normalize_text(p)]
    seen, out = set(), []
    for part in parts:
        day_match = DAY_PATTERN.search(part)
        time_match = TIME_PATTERN.search(part)
        if not day_match or not time_match:
            continue

        day = DAY_ALIASES.get(normalize_text(day_match.group(1)))
        s, e = parse_hhmm(time_match.group(1)), parse_hhmm(time_match.group(2))
        if not day or s is None or e is None or e <= s:
            continue

        key = (day, s, e)
        if key in seen:
            continue
        seen.add(key)
        out.append(TimeSlot(day=day, start_min=s, end_min=e))

    return out


def parse_exam_slot(exam_day_text: str, exam_time_text: str) -> Optional[ExamSlot]:
    day = normalize_text(exam_day_text)
    if not day:
        return None
    m = TIME_PATTERN.search(normalize_text(exam_time_text))
    if not m:
        return None
    s, e = parse_hhmm(m.group(1)), parse_hhmm(m.group(2))
    if s is None or e is None or e <= s:
        return None
    return ExamSlot(day=day, start_min=s, end_min=e)


def resolve_column(df: pd.DataFrame, logical_name: str) -> Optional[str]:
    existing = {normalize_text(c): c for c in df.columns}
    for alias in COLUMN_ALIASES.get(logical_name, ()):
        if normalize_text(alias) in existing:
            return existing[normalize_text(alias)]
    return None


def course_name_key(name: str) -> str:
    text = normalize_text(name).lower()
    text = text.replace("‌", " ")
    text = re.sub(r"\s+", "", text)
    text = re.sub("[^0-9a-zA-Z_؀-ۿ]", "", text)
    return text


TA_MARKERS = (
    "تدریسیار",
    "تدریسیاری",
    "حل تمرین",
    "حل‌تمرین",
    "tutorial",
)


def strip_ta_markers(name: str) -> str:
    text = normalize_text(name).lower()
    for marker in TA_MARKERS:
        text = text.replace(marker, " ")
    text = re.sub(r"\bta\b|\bt\.a\b|\bt a\b", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def is_ta_course_name(name: str) -> bool:
    lower = normalize_text(name).lower()
    for marker in TA_MARKERS:
        if marker in lower:
            return True
    return bool(re.search(r"\bta\b|\bt\.a\b|\bt a\b", lower))


def ta_base_key(ta_name: str) -> str:
    text = strip_ta_markers(ta_name)
    return course_name_key(text)


class SchedulerApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("چینش برنامه انتخاب واحد")
        self.geometry("1450x900")
        self.minsize(1200, 760)

        self.file_path_var = tk.StringVar()
        self.status_var = tk.StringVar(value="آماده")
        self.max_schedules_var = tk.StringVar(value="500")
        self.max_units_var = tk.StringVar(value="24")
        self.block_day_var = tk.StringVar(value=DAY_ORDER[0])
        self.block_start_var = tk.StringVar(value="08:00")
        self.block_end_var = tk.StringVar(value="10:00")
        self.schedule_info_var = tk.StringVar(value="برنامه‌ای تولید نشده است")
        self.total_units_var = tk.StringVar(value="مجموع واحد: 0")
        self.exclude_full_capacity_var = tk.BooleanVar(value=False)
        self.only_selected_courses_var = tk.BooleanVar(value=False)
        self.chart_scale_var = tk.DoubleVar(value=1.0)

        self.offers: List[CourseOffer] = []
        self.blocked_slots: List[TimeSlot] = []
        self.generated_schedules: List[List[CourseOffer]] = []
        self.current_schedule_index = 0
        self.exclusive_groups: List[List[str]] = []
        self.must_pick_group_map: Dict[str, str] = {}
        self.custom_prereq_map: Dict[str, set[str]] = {}
        self.custom_coreq_map: Dict[str, set[str]] = {}
        self.offer_picker_keys: List[Tuple[str, str]] = []
        self.offer_picker_labels: List[str] = []
        self.dependency_rule_entries: List[Tuple[str, str]] = []
        self.result_window: Optional[tk.Toplevel] = None
        self.weekly_canvas: Optional[tk.Canvas] = None
        self.exam_tree: Optional[ttk.Treeview] = None
        self.detail_tree: Optional[ttk.Treeview] = None
        self.group_builder_listbox: Optional[tk.Listbox] = None
        self.exclusive_groups_listbox: Optional[tk.Listbox] = None
        self.must_pick_offer_listbox: Optional[tk.Listbox] = None
        self.must_pick_selected_listbox: Optional[tk.Listbox] = None
        self.dep_target_listbox: Optional[tk.Listbox] = None
        self.dep_required_listbox: Optional[tk.Listbox] = None
        self.dep_rules_listbox: Optional[tk.Listbox] = None
        self.dep_mode_var = tk.StringVar(value="prereq")

        self._build_ui()

    def _build_ui(self) -> None:
        self.columnconfigure(0, weight=1)
        self.rowconfigure(3, weight=1)

        file_frame = ttk.LabelFrame(self, text="فایل ورودی", padding=8)
        file_frame.grid(row=0, column=0, sticky="ew", padx=10, pady=(10, 6))
        file_frame.columnconfigure(1, weight=1)
        ttk.Button(file_frame, text="انتخاب فایل", command=self.choose_file).grid(row=0, column=0, padx=5, pady=5)
        ttk.Entry(file_frame, textvariable=self.file_path_var).grid(row=0, column=1, sticky="ew", padx=5, pady=5)
        ttk.Button(file_frame, text="بارگذاری", command=self.load_file).grid(row=0, column=2, padx=5, pady=5)

        filters_frame = ttk.LabelFrame(self, text="فیلترها", padding=8)
        filters_frame.grid(row=1, column=0, sticky="ew", padx=10, pady=6)
        for col in range(4):
            filters_frame.columnconfigure(col, weight=1)
        ttk.Label(filters_frame, text="درس‌هایی که حتما برداشته شوند").grid(row=0, column=0, sticky="w")
        ttk.Label(filters_frame, text="درس‌هایی که برداشته نشوند").grid(row=0, column=1, sticky="w")
        ttk.Label(filters_frame, text="استادهایی که برداشته نشوند").grid(row=0, column=2, sticky="w")
        ttk.Label(filters_frame, text="زمان‌های ممنوع").grid(row=0, column=3, sticky="w")

        self.required_listbox = tk.Listbox(filters_frame, selectmode=tk.MULTIPLE, height=10, exportselection=False)
        self.required_listbox.grid(row=1, column=0, sticky="nsew", padx=5, pady=5)
        self.banned_courses_listbox = tk.Listbox(filters_frame, selectmode=tk.MULTIPLE, height=10, exportselection=False)
        self.banned_courses_listbox.grid(row=1, column=1, sticky="nsew", padx=5, pady=5)
        self.banned_instructors_listbox = tk.Listbox(filters_frame, selectmode=tk.MULTIPLE, height=10, exportselection=False)
        self.banned_instructors_listbox.grid(row=1, column=2, sticky="nsew", padx=5, pady=5)

        right_panel = ttk.Frame(filters_frame)
        right_panel.grid(row=1, column=3, sticky="nsew", padx=5, pady=5)
        for c in range(2):
            right_panel.columnconfigure(c, weight=1)
        ttk.Label(right_panel, text="روز").grid(row=0, column=0, sticky="w")
        ttk.Label(right_panel, text="از").grid(row=0, column=1, sticky="w")
        ttk.Combobox(
            right_panel, values=DAY_ORDER, textvariable=self.block_day_var, state="readonly"
        ).grid(row=1, column=0, sticky="ew", padx=(0, 4), pady=3)
        ttk.Entry(right_panel, textvariable=self.block_start_var).grid(row=1, column=1, sticky="ew", pady=3)
        ttk.Label(right_panel, text="تا").grid(row=2, column=0, sticky="w")
        ttk.Entry(right_panel, textvariable=self.block_end_var).grid(row=2, column=1, sticky="ew", pady=3)
        btns = ttk.Frame(right_panel)
        btns.grid(row=3, column=0, columnspan=2, sticky="ew")
        ttk.Button(btns, text="افزودن بازه", command=self.add_blocked_slot).pack(side=tk.LEFT, padx=(0, 4), pady=4)
        ttk.Button(btns, text="حذف انتخابی", command=self.remove_blocked_slot).pack(side=tk.LEFT, pady=4)
        self.blocked_listbox = tk.Listbox(right_panel, height=6, exportselection=False)
        self.blocked_listbox.grid(row=4, column=0, columnspan=2, sticky="nsew", pady=(6, 0))
        right_panel.rowconfigure(4, weight=1)

        advanced_frame = ttk.LabelFrame(filters_frame, text="قوانین پیشرفته", padding=6)
        advanced_frame.grid(row=2, column=0, columnspan=4, sticky="nsew", padx=5, pady=(8, 0))
        advanced_frame.columnconfigure(0, weight=1)
        advanced_frame.columnconfigure(1, weight=1)
        advanced_frame.rowconfigure(1, weight=1)

        exclusive_frame = ttk.LabelFrame(advanced_frame, text="گروه‌بندی دروس (حداکثر یکی از لیست)", padding=6)
        exclusive_frame.grid(row=0, column=0, sticky="nsew", padx=(0, 6))
        exclusive_frame.columnconfigure(0, weight=1)
        exclusive_frame.columnconfigure(1, weight=1)
        exclusive_frame.rowconfigure(1, weight=1)
        exclusive_frame.rowconfigure(3, weight=1)

        ttk.Label(exclusive_frame, text="از لیست زیر درس‌ها را انتخاب کن و گروه بساز").grid(
            row=0, column=0, columnspan=2, sticky="w", pady=(0, 4)
        )
        self.group_builder_listbox = tk.Listbox(
            exclusive_frame, selectmode=tk.MULTIPLE, height=6, exportselection=False
        )
        self.group_builder_listbox.grid(row=1, column=0, columnspan=2, sticky="nsew")
        ttk.Button(exclusive_frame, text="افزودن گروه محدودیت", command=self.add_exclusive_group).grid(
            row=2, column=0, sticky="ew", pady=(6, 4), padx=(0, 4)
        )
        ttk.Button(exclusive_frame, text="حذف گروه انتخابی", command=self.remove_exclusive_group).grid(
            row=2, column=1, sticky="ew", pady=(6, 4)
        )
        self.exclusive_groups_listbox = tk.Listbox(exclusive_frame, height=5, exportselection=False)
        self.exclusive_groups_listbox.grid(row=3, column=0, columnspan=2, sticky="nsew")

        mandatory_frame = ttk.LabelFrame(advanced_frame, text="گروه‌های اجباری دقیق", padding=6)
        mandatory_frame.grid(row=0, column=1, sticky="nsew", padx=(6, 0))
        mandatory_frame.columnconfigure(0, weight=1)
        mandatory_frame.columnconfigure(1, weight=1)
        mandatory_frame.rowconfigure(1, weight=1)
        mandatory_frame.rowconfigure(3, weight=1)
        ttk.Label(
            mandatory_frame,
            text="گروه دقیق (مثلا آز فیزیک۴ - دوشنبه) را انتخاب کن تا حتما در برنامه باشد",
        ).grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 4))
        self.must_pick_offer_listbox = tk.Listbox(
            mandatory_frame, selectmode=tk.MULTIPLE, height=6, exportselection=False
        )
        self.must_pick_offer_listbox.grid(row=1, column=0, columnspan=2, sticky="nsew")
        ttk.Button(mandatory_frame, text="افزودن به اجباری‌ها", command=self.add_mandatory_group).grid(
            row=2, column=0, sticky="ew", pady=(6, 4), padx=(0, 4)
        )
        ttk.Button(mandatory_frame, text="حذف اجباری انتخابی", command=self.remove_mandatory_group).grid(
            row=2, column=1, sticky="ew", pady=(6, 4)
        )
        self.must_pick_selected_listbox = tk.Listbox(mandatory_frame, height=5, exportselection=False)
        self.must_pick_selected_listbox.grid(row=3, column=0, columnspan=2, sticky="nsew")

        dependency_frame = ttk.LabelFrame(advanced_frame, text="پیش‌نیاز / هم‌نیاز سفارشی", padding=6)
        dependency_frame.grid(row=1, column=0, columnspan=2, sticky="nsew", pady=(8, 0))
        dependency_frame.columnconfigure(0, weight=1)
        dependency_frame.columnconfigure(1, weight=1)
        dependency_frame.columnconfigure(2, weight=1)
        dependency_frame.rowconfigure(1, weight=1)

        ttk.Label(dependency_frame, text="درس هدف").grid(row=0, column=0, sticky="w")
        ttk.Label(dependency_frame, text="درس‌های وابسته").grid(row=0, column=1, sticky="w")
        ttk.Label(dependency_frame, text="قوانین ثبت‌شده").grid(row=0, column=2, sticky="w")

        self.dep_target_listbox = tk.Listbox(dependency_frame, selectmode=tk.SINGLE, height=6, exportselection=False)
        self.dep_target_listbox.grid(row=1, column=0, sticky="nsew", padx=(0, 5))
        self.dep_required_listbox = tk.Listbox(
            dependency_frame, selectmode=tk.MULTIPLE, height=6, exportselection=False
        )
        self.dep_required_listbox.grid(row=1, column=1, sticky="nsew", padx=5)
        self.dep_rules_listbox = tk.Listbox(dependency_frame, height=6, exportselection=False)
        self.dep_rules_listbox.grid(row=1, column=2, sticky="nsew", padx=(5, 0))

        dep_btns = ttk.Frame(dependency_frame)
        dep_btns.grid(row=2, column=0, columnspan=3, sticky="ew", pady=(6, 0))
        ttk.Radiobutton(dep_btns, text="پیش‌نیاز", value="prereq", variable=self.dep_mode_var).pack(side=tk.LEFT, padx=(0, 8))
        ttk.Radiobutton(dep_btns, text="هم‌نیاز", value="coreq", variable=self.dep_mode_var).pack(side=tk.LEFT, padx=(0, 12))
        ttk.Button(dep_btns, text="افزودن قانون", command=self.add_dependency_rule).pack(side=tk.LEFT, padx=(0, 6))
        ttk.Button(dep_btns, text="حذف قانون انتخابی", command=self.remove_dependency_rule).pack(side=tk.LEFT)

        action_frame = ttk.Frame(self, padding=(10, 4, 10, 4))
        action_frame.grid(row=2, column=0, sticky="ew")
        action_frame.columnconfigure(10, weight=1)
        ttk.Label(action_frame, text="حداکثر تعداد برنامه").grid(row=0, column=0, padx=(0, 4))
        ttk.Entry(action_frame, textvariable=self.max_schedules_var, width=8).grid(row=0, column=1, padx=(0, 10))
        ttk.Label(action_frame, text="سقف واحد").grid(row=0, column=2, padx=(0, 4))
        ttk.Entry(action_frame, textvariable=self.max_units_var, width=7).grid(row=0, column=3, padx=(0, 10))
        ttk.Button(action_frame, text="تولید برنامه‌ها", command=self.generate_schedules).grid(row=0, column=4, padx=(0, 8))
        ttk.Checkbutton(
            action_frame,
            text="درس‌های ظرفیت تکمیل حذف شوند",
            variable=self.exclude_full_capacity_var,
        ).grid(row=0, column=5, padx=(0, 10), sticky="w")
        ttk.Checkbutton(
            action_frame,
            text="فقط درس‌های انتخاب‌شده ساخته شوند",
            variable=self.only_selected_courses_var,
        ).grid(row=0, column=6, padx=(0, 10), sticky="w")
        ttk.Label(action_frame, text="نمایش خروجی در پنجره جداگانه انجام می‌شود.").grid(
            row=0, column=7, columnspan=4, sticky="w"
        )

        ttk.Label(self, textvariable=self.status_var, anchor="e").grid(row=4, column=0, sticky="ew", padx=10, pady=(0, 8))

    def set_status(self, message: str) -> None:
        self.status_var.set(message)
        self.update_idletasks()

    def _on_result_window_close(self) -> None:
        if self.result_window is not None:
            try:
                self.result_window.destroy()
            except Exception:
                pass
        self.result_window = None
        self.weekly_canvas = None
        self.exam_tree = None
        self.detail_tree = None

    def _ensure_result_window(self) -> None:
        if self.result_window is not None and self.result_window.winfo_exists():
            return

        window = tk.Toplevel(self)
        window.title("خروجی برنامه‌ها")
        window.geometry("1300x760")
        window.minsize(1050, 620)
        window.protocol("WM_DELETE_WINDOW", self._on_result_window_close)
        window.rowconfigure(1, weight=1)
        window.columnconfigure(0, weight=1)

        controls = ttk.Frame(window, padding=(10, 10, 10, 0))
        controls.grid(row=0, column=0, sticky="ew")
        controls.columnconfigure(6, weight=1)
        ttk.Button(controls, text="برنامه قبلی", command=self.show_prev_schedule).grid(row=0, column=0, padx=(0, 6))
        ttk.Button(controls, text="برنامه بعدی", command=self.show_next_schedule).grid(row=0, column=1, padx=(0, 6))
        ttk.Button(controls, text="خروجی Excel", command=self.export_excel).grid(row=0, column=2, padx=(0, 12))
        ttk.Button(controls, text="کوچک‌تر", command=self.decrease_chart_scale).grid(row=0, column=3, padx=(0, 4))
        ttk.Button(controls, text="بزرگ‌تر", command=self.increase_chart_scale).grid(row=0, column=4, padx=(0, 12))
        ttk.Label(controls, textvariable=self.schedule_info_var).grid(row=0, column=5, sticky="w")
        ttk.Label(controls, textvariable=self.total_units_var).grid(row=0, column=6, sticky="e")

        result_frame = ttk.LabelFrame(window, text="نمایش برنامه", padding=8)
        result_frame.grid(row=1, column=0, sticky="nsew", padx=10, pady=10)
        result_frame.rowconfigure(0, weight=4)
        result_frame.rowconfigure(1, weight=2)
        result_frame.rowconfigure(2, weight=2)
        result_frame.columnconfigure(0, weight=1)

        weekly_canvas = tk.Canvas(result_frame, bg="white")
        weekly_canvas.grid(row=0, column=0, sticky="nsew", pady=(0, 6))

        exam_frame = ttk.LabelFrame(result_frame, text="جدول امتحان‌ها", padding=6)
        exam_frame.grid(row=1, column=0, sticky="nsew", pady=(0, 6))
        exam_frame.rowconfigure(0, weight=1)
        exam_frame.columnconfigure(0, weight=1)
        exam_cols = ("course_name", "group", "exam_day", "exam_time")
        exam_tree = ttk.Treeview(exam_frame, columns=exam_cols, show="headings")
        for key, title, width in [
            ("course_name", "نام درس", 260),
            ("group", "گروه", 70),
            ("exam_day", "روز امتحان", 180),
            ("exam_time", "زمان امتحان", 180),
        ]:
            exam_tree.heading(key, text=title)
            exam_tree.column(key, width=width, anchor="center")
        exam_tree.grid(row=0, column=0, sticky="nsew")
        exam_scroll = ttk.Scrollbar(exam_frame, orient=tk.VERTICAL, command=exam_tree.yview)
        exam_tree.configure(yscrollcommand=exam_scroll.set)
        exam_scroll.grid(row=0, column=1, sticky="ns")

        table_frame = ttk.Frame(result_frame)
        table_frame.grid(row=2, column=0, sticky="nsew")
        table_frame.rowconfigure(0, weight=1)
        table_frame.columnconfigure(0, weight=1)
        cols = ("course_name", "group", "instructor", "time", "exam")
        detail_tree = ttk.Treeview(table_frame, columns=cols, show="headings")
        for key, title, width in [
            ("course_name", "نام درس", 260),
            ("group", "گروه", 60),
            ("instructor", "مدرس", 220),
            ("time", "زمان/مکان ارائه", 360),
            ("exam", "امتحان", 220),
        ]:
            detail_tree.heading(key, text=title)
            detail_tree.column(key, width=width, anchor="center")
        detail_tree.grid(row=0, column=0, sticky="nsew")
        scroll = ttk.Scrollbar(table_frame, orient=tk.VERTICAL, command=detail_tree.yview)
        detail_tree.configure(yscrollcommand=scroll.set)
        scroll.grid(row=0, column=1, sticky="ns")

        weekly_canvas.bind("<Configure>", lambda _: self._redraw_current_schedule())

        self.result_window = window
        self.weekly_canvas = weekly_canvas
        self.exam_tree = exam_tree
        self.detail_tree = detail_tree

    def increase_chart_scale(self) -> None:
        self.chart_scale_var.set(min(1.8, self.chart_scale_var.get() + 0.1))
        self._redraw_current_schedule()

    def decrease_chart_scale(self) -> None:
        self.chart_scale_var.set(max(0.6, self.chart_scale_var.get() - 0.1))
        self._redraw_current_schedule()

    def choose_file(self) -> None:
        path = filedialog.askopenfilename(
            title="انتخاب فایل خروجی برنامه قبلی",
            filetypes=[("Excel/CSV", "*.xlsx *.xls *.csv"), ("All Files", "*.*")],
        )
        if path:
            self.file_path_var.set(path)

    def load_file(self) -> None:
        path = normalize_text(self.file_path_var.get())
        if not path:
            messagebox.showwarning("فایل ورودی", "ابتدا فایل را انتخاب کنید.")
            return
        file_path = Path(path)
        if not file_path.exists():
            messagebox.showerror("خطا", "فایل انتخاب‌شده وجود ندارد.")
            return

        try:
            df = pd.read_excel(file_path) if file_path.suffix.lower() in (".xlsx", ".xls") else pd.read_csv(file_path)
        except Exception as exc:
            messagebox.showerror("خطا", f"خواندن فایل انجام نشد:\n{exc}")
            return

        offers = self._parse_offers(df)
        if not offers:
            messagebox.showwarning("بدون داده", "هیچ گروه درسی قابل استفاده پیدا نشد.")
            return
        self.offers = offers
        self.generated_schedules = []
        self.current_schedule_index = 0
        self._fill_filter_listboxes()
        self._clear_result_views()
        self.set_status(f"{len(self.offers)} گروه درسی بارگذاری شد.")

    def _parse_offers(self, df: pd.DataFrame) -> List[CourseOffer]:
        c_name = resolve_column(df, "course_name")
        c_group = resolve_column(df, "course_group")
        c_time = resolve_column(df, "time_location")
        c_slots = resolve_column(df, "class_time_slots")
        c_time_1 = resolve_column(df, "class_time_1")
        c_time_2 = resolve_column(df, "class_time_2")
        c_location = resolve_column(df, "class_location")
        if not c_name or not c_group or (not c_time and not c_slots and not c_time_1 and not c_time_2):
            messagebox.showerror(
                "ستون‌های لازم موجود نیست",
                "فایل باید ستون‌های «نام درس»، «گروه درس» و یکی از «زمان/مکان ارائه»، «بازه‌های زمانی کلاس»، «تایم اول/تایم دوم» را داشته باشد.",
            )
            return []

        c_num = resolve_column(df, "course_number")
        c_ins = resolve_column(df, "instructor")
        c_exd = resolve_column(df, "exam_day")
        c_ext = resolve_column(df, "exam_time")
        c_cap = resolve_column(df, "capacity_registered_waiting")
        c_units = resolve_column(df, "units")

        out: List[CourseOffer] = []
        seen = set()
        for _, row in df.iterrows():
            name = normalize_text(row.get(c_name, ""))
            group = normalize_text(row.get(c_group, ""))
            time_loc = normalize_text(row.get(c_time, "")) if c_time else ""
            class_slots_text = normalize_text(row.get(c_slots, "")) if c_slots else ""
            time_1 = normalize_text(row.get(c_time_1, "")) if c_time_1 else ""
            time_2 = normalize_text(row.get(c_time_2, "")) if c_time_2 else ""
            class_location = normalize_text(row.get(c_location, "")) if c_location else ""

            if not name or not group or (not time_loc and not class_slots_text and not time_1 and not time_2):
                continue
            course_number = normalize_text(row.get(c_num, "")) if c_num else ""
            instructor = normalize_text(row.get(c_ins, "")) if c_ins else ""
            exam_day = normalize_text(row.get(c_exd, "")) if c_exd else ""
            exam_time = normalize_text(row.get(c_ext, "")) if c_ext else ""
            capacity_text = normalize_text(row.get(c_cap, "")) if c_cap else ""
            units_text = normalize_text(row.get(c_units, "")) if c_units else ""
            unit_value = parse_units_total(units_text)

            parsed_slots: List[TimeSlot] = []
            seen_slot_keys = set()

            for slot_text in (time_1, time_2):
                slot = parse_single_slot_text(slot_text)
                if not slot:
                    continue
                key_slot = (slot.day, slot.start_min, slot.end_min)
                if key_slot in seen_slot_keys:
                    continue
                seen_slot_keys.add(key_slot)
                parsed_slots.append(slot)

            if not parsed_slots:
                compact_slots = parse_class_slots_compact(class_slots_text)
                parsed_slots = compact_slots if compact_slots else parse_class_slots(class_slots_text)
                if not parsed_slots:
                    parsed_slots = parse_class_slots(time_loc)
            if not parsed_slots:
                continue

            if not time_1 and parsed_slots:
                time_1 = format_slot(parsed_slots[0])
            if not time_2 and len(parsed_slots) > 1:
                time_2 = format_slot(parsed_slots[1])

            if not time_loc:
                time_parts = [x for x in (time_1, time_2) if x]
                if not time_parts:
                    time_parts.append(format_slots(parsed_slots))
                if class_location:
                    time_parts.append(class_location)
                time_loc = " | ".join(time_parts)

            key = (
                name,
                group,
                time_loc,
                class_slots_text,
                time_1,
                time_2,
                class_location,
                exam_day,
                exam_time,
                instructor,
            )
            if key in seen:
                continue
            seen.add(key)
            out.append(
                CourseOffer(
                    course_number=course_number,
                    course_name=name,
                    course_group=group,
                    instructor=instructor,
                    time_location=time_loc,
                    exam_day=exam_day,
                    exam_time=exam_time,
                    class_time_1=time_1,
                    class_time_2=time_2,
                    class_location=class_location,
                    units_text=units_text,
                    unit_value=unit_value,
                    capacity_registered_waiting=capacity_text,
                    class_slots=parsed_slots,
                    exam_slot=parse_exam_slot(exam_day, exam_time),
                    is_full=parse_capacity_full(capacity_text),
                    instructor_tokens=split_instructor_names(instructor),
                )
            )
        return out

    def _fill_filter_listboxes(self) -> None:
        self.required_listbox.delete(0, tk.END)
        self.banned_courses_listbox.delete(0, tk.END)
        self.banned_instructors_listbox.delete(0, tk.END)
        courses = sorted({x.course_name for x in self.offers})
        for c in courses:
            self.required_listbox.insert(tk.END, c)
            self.banned_courses_listbox.insert(tk.END, c)
        for i in sorted({n for x in self.offers for n in x.instructor_tokens}):
            self.banned_instructors_listbox.insert(tk.END, i)
        self._refresh_advanced_filters(courses)

    def _refresh_advanced_filters(self, courses: List[str]) -> None:
        existing_courses = set(courses)

        # Keep only valid exclusive groups
        cleaned_groups: List[List[str]] = []
        for group in self.exclusive_groups:
            valid = sorted({c for c in group if c in existing_courses})
            if len(valid) >= 2:
                cleaned_groups.append(valid)
        self.exclusive_groups = cleaned_groups

        # Keep only valid mandatory picks
        valid_offer_keys = {(o.course_name, o.course_group) for o in self.offers}
        self.must_pick_group_map = {
            c: g for c, g in self.must_pick_group_map.items() if (c, g) in valid_offer_keys
        }

        cleaned_prereq: Dict[str, set[str]] = {}
        for course, deps in self.custom_prereq_map.items():
            if course not in existing_courses:
                continue
            valid = {d for d in deps if d in existing_courses and d != course}
            if valid:
                cleaned_prereq[course] = valid
        self.custom_prereq_map = cleaned_prereq

        cleaned_coreq: Dict[str, set[str]] = {}
        for course, deps in self.custom_coreq_map.items():
            if course not in existing_courses:
                continue
            valid = {d for d in deps if d in existing_courses and d != course}
            if valid:
                cleaned_coreq[course] = valid
        self.custom_coreq_map = cleaned_coreq

        if self.group_builder_listbox is not None:
            self.group_builder_listbox.delete(0, tk.END)
            for c in courses:
                self.group_builder_listbox.insert(tk.END, c)

        # Populate selectable offer list for mandatory exact groups
        self.offer_picker_keys = sorted(valid_offer_keys, key=lambda x: (x[0], x[1]))
        self.offer_picker_labels = [f"{c} | گروه {g}" for c, g in self.offer_picker_keys]
        if self.must_pick_offer_listbox is not None:
            self.must_pick_offer_listbox.delete(0, tk.END)
            for label in self.offer_picker_labels:
                self.must_pick_offer_listbox.insert(tk.END, label)

        if self.dep_target_listbox is not None:
            self.dep_target_listbox.delete(0, tk.END)
            for c in courses:
                self.dep_target_listbox.insert(tk.END, c)
        if self.dep_required_listbox is not None:
            self.dep_required_listbox.delete(0, tk.END)
            for c in courses:
                self.dep_required_listbox.insert(tk.END, c)

        self._refresh_exclusive_groups_listbox()
        self._refresh_mandatory_groups_listbox()
        self._refresh_dependency_rules_listbox()

    def _refresh_exclusive_groups_listbox(self) -> None:
        if self.exclusive_groups_listbox is None:
            return
        self.exclusive_groups_listbox.delete(0, tk.END)
        for idx, group in enumerate(self.exclusive_groups, start=1):
            self.exclusive_groups_listbox.insert(tk.END, f"{idx}) " + " | ".join(group))

    def _refresh_mandatory_groups_listbox(self) -> None:
        if self.must_pick_selected_listbox is None:
            return
        self.must_pick_selected_listbox.delete(0, tk.END)
        for course in sorted(self.must_pick_group_map.keys()):
            self.must_pick_selected_listbox.insert(
                tk.END, f"{course} | گروه {self.must_pick_group_map[course]}"
            )

    def add_exclusive_group(self) -> None:
        if self.group_builder_listbox is None:
            return
        selected = [normalize_text(self.group_builder_listbox.get(i)) for i in self.group_builder_listbox.curselection()]
        selected = sorted({s for s in selected if s})
        if len(selected) < 2:
            messagebox.showwarning("گروه‌بندی", "حداقل دو درس را برای گروه محدودیت انتخاب کنید.")
            return

        selected_set = set(selected)
        for group in self.exclusive_groups:
            if set(group) == selected_set:
                return

        self.exclusive_groups.append(selected)
        self.exclusive_groups.sort(key=lambda g: (len(g), g))
        self._refresh_exclusive_groups_listbox()

    def remove_exclusive_group(self) -> None:
        if self.exclusive_groups_listbox is None:
            return
        indices = list(self.exclusive_groups_listbox.curselection())
        for idx in reversed(indices):
            if 0 <= idx < len(self.exclusive_groups):
                self.exclusive_groups.pop(idx)
        self._refresh_exclusive_groups_listbox()

    def add_mandatory_group(self) -> None:
        if self.must_pick_offer_listbox is None:
            return
        indices = list(self.must_pick_offer_listbox.curselection())
        if not indices:
            return
        for idx in indices:
            if 0 <= idx < len(self.offer_picker_keys):
                course_name, course_group = self.offer_picker_keys[idx]
                self.must_pick_group_map[course_name] = course_group
        self._refresh_mandatory_groups_listbox()

    def remove_mandatory_group(self) -> None:
        if self.must_pick_selected_listbox is None:
            return
        indices = list(self.must_pick_selected_listbox.curselection())
        if not indices:
            return
        sorted_courses = sorted(self.must_pick_group_map.keys())
        for idx in reversed(indices):
            if 0 <= idx < len(sorted_courses):
                self.must_pick_group_map.pop(sorted_courses[idx], None)
        self._refresh_mandatory_groups_listbox()

    def _refresh_dependency_rules_listbox(self) -> None:
        if self.dep_rules_listbox is None:
            return
        self.dep_rules_listbox.delete(0, tk.END)
        self.dependency_rule_entries = []

        for course in sorted(self.custom_prereq_map.keys()):
            deps = " + ".join(sorted(self.custom_prereq_map[course]))
            self.dep_rules_listbox.insert(tk.END, f"پیش‌نیاز | {course} <- {deps}")
            self.dependency_rule_entries.append(("prereq", course))

        for course in sorted(self.custom_coreq_map.keys()):
            deps = " + ".join(sorted(self.custom_coreq_map[course]))
            self.dep_rules_listbox.insert(tk.END, f"هم‌نیاز | {course} <-> {deps}")
            self.dependency_rule_entries.append(("coreq", course))

    def add_dependency_rule(self) -> None:
        if self.dep_target_listbox is None or self.dep_required_listbox is None:
            return
        target_sel = list(self.dep_target_listbox.curselection())
        dep_sel = list(self.dep_required_listbox.curselection())
        if not target_sel:
            messagebox.showwarning("قانون وابستگی", "ابتدا یک درس هدف انتخاب کنید.")
            return
        if not dep_sel:
            messagebox.showwarning("قانون وابستگی", "حداقل یک درس وابسته انتخاب کنید.")
            return

        target = normalize_text(self.dep_target_listbox.get(target_sel[0]))
        deps = {
            normalize_text(self.dep_required_listbox.get(i))
            for i in dep_sel
            if normalize_text(self.dep_required_listbox.get(i)) != target
        }
        if not deps:
            messagebox.showwarning("قانون وابستگی", "درس هدف نمی‌تواند وابسته به خودش باشد.")
            return

        if self.dep_mode_var.get() == "coreq":
            self.custom_coreq_map.setdefault(target, set()).update(deps)
        else:
            self.custom_prereq_map.setdefault(target, set()).update(deps)
        self._refresh_dependency_rules_listbox()

    def remove_dependency_rule(self) -> None:
        if self.dep_rules_listbox is None:
            return
        indices = list(self.dep_rules_listbox.curselection())
        if not indices:
            return
        for idx in reversed(indices):
            if 0 <= idx < len(self.dependency_rule_entries):
                mode, course = self.dependency_rule_entries[idx]
                if mode == "coreq":
                    self.custom_coreq_map.pop(course, None)
                else:
                    self.custom_prereq_map.pop(course, None)
        self._refresh_dependency_rules_listbox()

    def add_blocked_slot(self) -> None:
        day = normalize_day(self.block_day_var.get())
        s = parse_hhmm(normalize_text(self.block_start_var.get()))
        e = parse_hhmm(normalize_text(self.block_end_var.get()))
        if not day or s is None or e is None or e <= s:
            messagebox.showwarning("ورودی نامعتبر", "روز یا ساعت نامعتبر است.")
            return
        slot = TimeSlot(day=day, start_min=s, end_min=e)
        if slot not in self.blocked_slots:
            self.blocked_slots.append(slot)
            self._refresh_blocked_listbox()

    def remove_blocked_slot(self) -> None:
        sel = list(self.blocked_listbox.curselection())
        for i in reversed(sel):
            if 0 <= i < len(self.blocked_slots):
                self.blocked_slots.pop(i)
        self._refresh_blocked_listbox()

    def _refresh_blocked_listbox(self) -> None:
        self.blocked_listbox.delete(0, tk.END)
        for x in self.blocked_slots:
            self.blocked_listbox.insert(tk.END, f"{x.day} | {minutes_to_hhmm(x.start_min)}-{minutes_to_hhmm(x.end_min)}")

    @staticmethod
    def _selected_values(lb: tk.Listbox) -> List[str]:
        return [normalize_text(lb.get(i)) for i in lb.curselection()]

    def _build_ta_coupling_maps(self, course_names: Sequence[str]) -> Tuple[Dict[str, set[str]], Dict[str, str]]:
        normal_courses = [c for c in course_names if not is_ta_course_name(c)]
        ta_courses = [c for c in course_names if is_ta_course_name(c)]

        normal_by_key: Dict[str, List[str]] = {}
        for c in normal_courses:
            normal_by_key.setdefault(course_name_key(c), []).append(c)

        ta_requirements: Dict[str, set[str]] = {}
        ta_to_base: Dict[str, str] = {}
        for ta in ta_courses:
            base_key = ta_base_key(ta)
            if not base_key:
                continue

            candidates = normal_by_key.get(base_key, [])
            if not candidates:
                fuzzy = [c for c in normal_courses if base_key in course_name_key(c) or course_name_key(c) in base_key]
                candidates = sorted(
                    fuzzy, key=lambda x: (abs(len(course_name_key(x)) - len(base_key)), len(course_name_key(x)))
                )
            if not candidates:
                continue

            base = candidates[0]
            ta_to_base[ta] = base
            ta_requirements.setdefault(base, set()).add(ta)

        return ta_requirements, ta_to_base

    def _violates_exclusive_groups(self, offer_name: str, selected_names: set[str]) -> bool:
        for group in self.exclusive_groups:
            group_set = set(group)
            if offer_name in group_set and len(selected_names & group_set) > 0:
                return True
        return False

    @staticmethod
    def _violates_ta_coupling(
        selected_names: set[str],
        ta_requirements: Dict[str, set[str]],
        ta_to_base: Dict[str, str],
    ) -> bool:
        for ta_name, base_name in ta_to_base.items():
            if ta_name in selected_names and base_name not in selected_names:
                return True
        for base_name, ta_names in ta_requirements.items():
            if base_name in selected_names and len(selected_names & ta_names) == 0:
                return True
        return False

    @staticmethod
    def _expand_required_by_dependencies(
        required: set[str],
        prereq_map: Dict[str, set[str]],
        coreq_map: Dict[str, set[str]],
    ) -> set[str]:
        expanded = set(required)
        while True:
            changed = False
            for course in list(expanded):
                for dep in prereq_map.get(course, set()) | coreq_map.get(course, set()):
                    if dep not in expanded:
                        expanded.add(dep)
                        changed = True
            if not changed:
                break
        return expanded

    @staticmethod
    def _violates_custom_dependencies(
        selected_names: set[str],
        prereq_map: Dict[str, set[str]],
        coreq_map: Dict[str, set[str]],
    ) -> bool:
        for course, deps in prereq_map.items():
            if course in selected_names and not deps.issubset(selected_names):
                return True
        for course, deps in coreq_map.items():
            if course in selected_names and not deps.issubset(selected_names):
                return True
        return False

    def generate_schedules(self) -> None:
        if not self.offers:
            messagebox.showwarning("No Data", "Load input file first.")
            return

        required = set(self._selected_values(self.required_listbox))
        banned_courses = set(self._selected_values(self.banned_courses_listbox))
        banned_instructors = set(self._selected_values(self.banned_instructors_listbox))
        mandatory_group_map = dict(self.must_pick_group_map)

        # Mandatory exact group implies required course.
        required |= set(mandatory_group_map.keys())

        # Expand required set by custom prerequisite/corequisite rules.
        required = self._expand_required_by_dependencies(required, self.custom_prereq_map, self.custom_coreq_map)

        both_required_and_banned = sorted(required & banned_courses)
        if both_required_and_banned:
            messagebox.showwarning(
                "Filter Conflict",
                "Courses are both required and banned:\n" + "\n".join(both_required_and_banned),
            )
            return

        both_banned_and_mandatory = sorted(set(mandatory_group_map.keys()) & banned_courses)
        if both_banned_and_mandatory:
            messagebox.showwarning(
                "Filter Conflict",
                "Courses are both mandatory-group and banned:\n" + "\n".join(both_banned_and_mandatory),
            )
            return

        try:
            max_count = int(normalize_text(self.max_schedules_var.get()) or "500")
        except ValueError:
            messagebox.showwarning("Max Schedules", "Enter a valid number.")
            return
        if max_count <= 0:
            messagebox.showwarning("Max Schedules", "Number must be greater than zero.")
            return

        try:
            max_units = float(normalize_text(self.max_units_var.get()) or "24")
        except ValueError:
            messagebox.showwarning("Max Units", "Enter a valid unit limit.")
            return
        if max_units <= 0:
            messagebox.showwarning("Max Units", "Unit limit must be greater than zero.")
            return

        usable = []
        for offer in self.offers:
            if offer.course_name in banned_courses:
                continue
            if self._offer_has_banned_instructor(offer, banned_instructors):
                continue
            must_group = mandatory_group_map.get(offer.course_name)
            if must_group and offer.course_group != must_group:
                continue
            if self.exclude_full_capacity_var.get() and offer.is_full and not must_group:
                continue
            usable.append(offer)

        by_course: Dict[str, List[CourseOffer]] = {}
        for offer in usable:
            by_course.setdefault(offer.course_name, []).append(offer)

        if not by_course:
            messagebox.showwarning("No Result", "No courses left after filters.")
            return

        missing = [c for c in sorted(required) if c not in by_course]
        if missing:
            messagebox.showwarning("Missing Courses", "Required courses not available after filters:\n" + "\n".join(missing))
            return

        dependency_missing: List[str] = []
        for course in sorted(required):
            deps = set(self.custom_prereq_map.get(course, set())) | set(self.custom_coreq_map.get(course, set()))
            miss = [d for d in sorted(deps) if d not in by_course]
            if miss:
                dependency_missing.append(f"{course}: " + ", ".join(miss))
        if dependency_missing:
            messagebox.showwarning(
                "Dependency Error",
                "Custom prereq/coreq courses not available after filters:\n" + "\n".join(dependency_missing),
            )
            return

        required_courses = [c for c in sorted(by_course.keys()) if c in required]
        optional_courses = [c for c in sorted(by_course.keys()) if c not in required]
        if self.only_selected_courses_var.get():
            if not required_courses:
                messagebox.showwarning(
                    "Course Selection",
                    "In only-selected mode, choose at least one required course.",
                )
                return
            optional_courses = []

        required_items = [(c, by_course[c], True) for c in required_courses]
        optional_items = [(c, by_course[c], False) for c in optional_courses]
        required_items.sort(key=lambda x: len(x[1]))
        optional_items.sort(key=lambda x: len(x[1]))
        course_items = required_items + optional_items

        all_course_names = sorted({o.course_name for o in self.offers})
        ta_requirements, ta_to_base = self._build_ta_coupling_maps(all_course_names)

        missing_ta_for_required: List[str] = []
        for base_name, ta_names in ta_requirements.items():
            if base_name in required and not any(ta in by_course for ta in ta_names):
                missing_ta_for_required.append(base_name)
        if missing_ta_for_required:
            messagebox.showwarning(
                "TA Coupling",
                "TA course not available for required courses:\n" + "\n".join(sorted(missing_ta_for_required)),
            )
            return

        required_min_suffix = [0.0] * (len(course_items) + 1)
        for idx in range(len(course_items) - 1, -1, -1):
            _, options, is_required = course_items[idx]
            min_this = min((o.unit_value for o in options), default=0.0) if is_required else 0.0
            required_min_suffix[idx] = required_min_suffix[idx + 1] + min_this

        self.set_status("Generating valid schedules...")
        results: List[List[CourseOffer]] = []
        cur: List[CourseOffer] = []
        selected_names: set[str] = set()
        eps = 1e-9

        def backtrack(idx: int, cur_units: float) -> None:
            if len(results) >= max_count:
                return
            if cur_units + required_min_suffix[idx] > max_units + eps:
                return

            if idx == len(course_items):
                if cur:
                    if self._violates_ta_coupling(selected_names, ta_requirements, ta_to_base):
                        return
                    if self._violates_custom_dependencies(selected_names, self.custom_prereq_map, self.custom_coreq_map):
                        return
                    results.append(cur.copy())
                return

            _, options, is_required = course_items[idx]
            if not is_required:
                backtrack(idx + 1, cur_units)
                if len(results) >= max_count:
                    return

            for offer in options:
                if cur_units + offer.unit_value > max_units + eps:
                    continue
                if self._violates_exclusive_groups(offer.course_name, selected_names):
                    continue
                if self._has_conflict(offer, cur, self.blocked_slots):
                    continue

                cur.append(offer)
                selected_names.add(offer.course_name)
                backtrack(idx + 1, cur_units + offer.unit_value)
                selected_names.discard(offer.course_name)
                cur.pop()
                if len(results) >= max_count:
                    return

        backtrack(0, 0.0)

        self.generated_schedules = results
        self.current_schedule_index = 0
        if not results:
            self.schedule_info_var.set("No valid schedule found.")
            self._clear_result_views()
            self.set_status("No schedule matched filters.")
            return

        self._show_schedule(0)
        if len(results) >= max_count:
            self.set_status(f"Generated up to {max_count} valid schedules.")
        else:
            self.set_status(f"Generated {len(results)} valid schedules.")

    @staticmethod
    def _offer_has_banned_instructor(offer: CourseOffer, banned: set[str]) -> bool:
        if not banned:
            return False
        for b in banned:
            if b and (b in offer.instructor or b in offer.instructor_tokens):
                return True
        return False

    def _has_conflict(self, offer: CourseOffer, selected: Sequence[CourseOffer], blocked: Sequence[TimeSlot]) -> bool:
        for slot in offer.class_slots:
            for b in blocked:
                if slot.day == b.day and overlap(slot.start_min, slot.end_min, b.start_min, b.end_min):
                    return True
        for chosen in selected:
            for a in offer.class_slots:
                for b in chosen.class_slots:
                    if a.day == b.day and overlap(a.start_min, a.end_min, b.start_min, b.end_min):
                        return True
            if offer.exam_slot and chosen.exam_slot and offer.exam_slot.day == chosen.exam_slot.day:
                if overlap(
                    offer.exam_slot.start_min,
                    offer.exam_slot.end_min,
                    chosen.exam_slot.start_min,
                    chosen.exam_slot.end_min,
                ):
                    return True
        return False

    def show_prev_schedule(self) -> None:
        if self.generated_schedules and self.current_schedule_index > 0:
            self.current_schedule_index -= 1
            self._show_schedule(self.current_schedule_index)

    def show_next_schedule(self) -> None:
        if self.generated_schedules and self.current_schedule_index < len(self.generated_schedules) - 1:
            self.current_schedule_index += 1
            self._show_schedule(self.current_schedule_index)

    def _show_schedule(self, index: int) -> None:
        if not (0 <= index < len(self.generated_schedules)):
            return
        self._ensure_result_window()
        schedule = self.generated_schedules[index]
        self.schedule_info_var.set(f"برنامه {index + 1} از {len(self.generated_schedules)}")
        total_units = sum(offer.unit_value for offer in schedule)
        units_display = int(total_units) if abs(total_units - int(total_units)) < 1e-6 else round(total_units, 2)
        self.total_units_var.set(f"مجموع واحد: {units_display}")
        self._draw_weekly_chart(schedule)
        self._fill_exam_table(schedule)
        self._fill_detail_table(schedule)
        if self.result_window is not None and self.result_window.winfo_exists():
            self.result_window.deiconify()
            self.result_window.lift()

    def _redraw_current_schedule(self) -> None:
        if self.generated_schedules:
            self._show_schedule(self.current_schedule_index)

    def _clear_result_views(self) -> None:
        if self.weekly_canvas is not None:
            self.weekly_canvas.delete("all")
        if self.exam_tree is not None:
            for item in self.exam_tree.get_children():
                self.exam_tree.delete(item)
        if self.detail_tree is not None:
            for item in self.detail_tree.get_children():
                self.detail_tree.delete(item)
        self.total_units_var.set("مجموع واحد: 0")

    def _fill_detail_table(self, schedule: Sequence[CourseOffer]) -> None:
        if self.detail_tree is None:
            return
        for item in self.detail_tree.get_children():
            self.detail_tree.delete(item)
        for offer in sorted(schedule, key=lambda x: (x.course_name, x.course_group)):
            exam = f"{offer.exam_day} | {offer.exam_time}".strip(" |") if (offer.exam_day or offer.exam_time) else ""
            time_display = offer.time_location if offer.time_location else format_slots(offer.class_slots)
            self.detail_tree.insert(
                "",
                tk.END,
                values=(offer.course_name, offer.course_group, offer.instructor, time_display, exam),
            )

    def _draw_weekly_chart(self, schedule: Sequence[CourseOffer]) -> None:
        if self.weekly_canvas is None:
            return

        c = self.weekly_canvas
        c.delete("all")

        scale = max(0.6, min(1.8, float(self.chart_scale_var.get())))
        w = max(c.winfo_width(), 900)
        h = max(c.winfo_height(), 320)

        header_h = int(42 * scale)
        left = int(72 * scale)
        top = header_h + int(22 * scale)
        right = int(24 * scale)
        bottom = int(24 * scale)

        grid_w = max(w - left - right, 260)
        grid_h = max(h - top - bottom, 170)
        day_w = grid_w / max(1, len(DAY_ORDER))

        title_font = ("Tahoma", max(9, int(11 * scale)), "bold")
        day_font = ("Tahoma", max(8, int(9 * scale)), "bold")
        time_font = ("Tahoma", max(7, int(8 * scale)))
        box_font = ("Tahoma", max(7, int(8 * scale)))

        c.create_rectangle(0, 0, w, h, fill="#F4F7FB", outline="")
        c.create_rectangle(0, 0, w, header_h, fill="#0F172A", outline="")
        c.create_text(
            w // 2,
            header_h // 2,
            text="Weekly Course Schedule",
            fill="#F8FAFC",
            font=title_font,
        )

        slots = [s for offer in schedule for s in offer.class_slots]
        if slots:
            min_t = (min(x.start_min for x in slots) // 60) * 60
            max_t = int(math.ceil(max(x.end_min for x in slots) / 60.0) * 60)
            if max_t - min_t < 300:
                max_t = min_t + 300
        else:
            min_t, max_t = 8 * 60, 20 * 60

        # Day columns
        for i, day in enumerate(DAY_ORDER):
            x1 = left + i * day_w
            x2 = left + (i + 1) * day_w
            col_fill = "#FFFFFF" if i % 2 == 0 else "#F8FBFF"
            c.create_rectangle(x1, top, x2, top + grid_h, fill=col_fill, outline="#D6DFEA")
            c.create_rectangle(x1, top - int(20 * scale), x2, top, fill="#E7EEF7", outline="#D6DFEA")
            c.create_text((x1 + x2) / 2, top - int(10 * scale), text=day, font=day_font, fill="#1E293B")

        # Time grid (30-minute granularity)
        t = min_t
        while t <= max_t:
            y = top + ((t - min_t) / (max_t - min_t)) * grid_h
            is_hour = (t % 60) == 0
            c.create_line(
                left,
                y,
                left + grid_w,
                y,
                fill="#CBD5E1" if is_hour else "#E2E8F0",
                width=1 if is_hour else 1,
            )
            if is_hour:
                c.create_text(left - int(8 * scale), y, text=minutes_to_hhmm(t), anchor="e", font=time_font, fill="#334155")
            t += 30

        # Blocked slots overlay
        for blocked in self.blocked_slots:
            if blocked.day not in DAY_ORDER:
                continue
            i = DAY_ORDER.index(blocked.day)
            x1 = left + i * day_w + 2
            x2 = left + (i + 1) * day_w - 2
            y1 = top + ((blocked.start_min - min_t) / (max_t - min_t)) * grid_h
            y2 = top + ((blocked.end_min - min_t) / (max_t - min_t)) * grid_h
            y1 = max(top + 1, y1)
            y2 = min(top + grid_h - 1, y2)
            if y2 <= y1:
                continue
            c.create_rectangle(x1, y1, x2, y2, fill="#FEE2E2", outline="#FCA5A5", stipple="gray25")

        palette = ["#DBEAFE", "#D1FAE5", "#FEF3C7", "#FCE7F3", "#E0E7FF", "#FDE68A", "#CCFBF1"]

        def color_for_offer(offer: CourseOffer) -> Tuple[str, str]:
            if offer.is_full:
                return "#FECACA", "#B91C1C"
            seed = sum(ord(ch) for ch in course_name_key(offer.course_name))
            fill = palette[seed % len(palette)]
            return fill, "#334155"

        for offer in schedule:
            fill, border = color_for_offer(offer)
            for slot in offer.class_slots:
                if slot.day not in DAY_ORDER:
                    continue
                i = DAY_ORDER.index(slot.day)
                x1 = left + i * day_w + 4
                x2 = left + (i + 1) * day_w - 4
                y1 = top + ((slot.start_min - min_t) / (max_t - min_t)) * grid_h + 2
                y2 = top + ((slot.end_min - min_t) / (max_t - min_t)) * grid_h - 2
                if y2 <= y1:
                    y2 = y1 + 2

                c.create_rectangle(x1, y1, x2, y2, fill=fill, outline=border, width=2)

                loc = f"\n{offer.class_location}" if offer.class_location else ""
                txt = (
                    f"{offer.course_name}\n"
                    f"Group {offer.course_group} | {minutes_to_hhmm(slot.start_min)}-{minutes_to_hhmm(slot.end_min)}"
                    f"{loc}"
                )
                c.create_text(
                    (x1 + x2) / 2,
                    (y1 + y2) / 2,
                    text=txt,
                    width=max(40, int(x2 - x1 - 10)),
                    font=box_font,
                    fill="#0F172A",
                    justify="center",
                )

        # Legend
        lx = left + 6
        ly = 8
        c.create_rectangle(lx, ly, lx + 14, ly + 14, fill="#FECACA", outline="#B91C1C")
        c.create_text(lx + 18, ly + 7, text="Full capacity", anchor="w", fill="#F8FAFC", font=time_font)

    def _fill_exam_table(self, schedule: Sequence[CourseOffer]) -> None:
        if self.exam_tree is None:
            return
        for item in self.exam_tree.get_children():
            self.exam_tree.delete(item)

        for offer in sorted(schedule, key=lambda x: (x.exam_day, x.exam_time, x.course_name, x.course_group)):
            self.exam_tree.insert(
                "",
                tk.END,
                values=(offer.course_name, offer.course_group, offer.exam_day, offer.exam_time),
            )

    def export_excel(self) -> None:
        if not self.generated_schedules:
            messagebox.showwarning("خروجی", "ابتدا برنامه‌ها را تولید کنید.")
            return
        path = filedialog.asksaveasfilename(
            title="ذخیره خروجی برنامه‌ها",
            defaultextension=".xlsx",
            filetypes=[("Excel", "*.xlsx"), ("All Files", "*.*")],
        )
        if not path:
            return
        rows = []
        for idx, schedule in enumerate(self.generated_schedules, start=1):
            for offer in schedule:
                rows.append(
                    {
                        "شماره برنامه": idx,
                        "شماره درس": offer.course_number,
                        "نام درس": offer.course_name,
                        "گروه درس": offer.course_group,
                        "مدرس": offer.instructor,
                        "زمان/مکان ارائه": offer.time_location,
                        "بازه‌های زمانی کلاس (استخراج‌شده)": format_slots(offer.class_slots),
                        "تایم اول": offer.class_time_1,
                        "تایم دوم": offer.class_time_2,
                        "محل برگزاری کلاس": offer.class_location,
                        "واحد تئوری/عملی": offer.units_text,
                        "واحد کل درس": offer.unit_value,
                        "روز امتحان": offer.exam_day,
                        "زمان امتحان": offer.exam_time,
                        "ظرفیت-ثبت نام شده-لیست انتظار": offer.capacity_registered_waiting,
                        "وضعیت ظرفیت": "تکمیل" if offer.is_full else "آزاد/نامشخص",
                    }
                )
        try:
            pd.DataFrame(rows).to_excel(path, index=False)
            messagebox.showinfo("موفق", "فایل خروجی ذخیره شد.")
        except Exception as exc:
            messagebox.showerror("خطا", f"ذخیره خروجی انجام نشد:\n{exc}")


def main() -> None:
    app = SchedulerApp()
    app.mainloop()


if __name__ == "__main__":
    main()
