from ortools.sat.python import cp_model
import pandas as pd
from open import ret

# Данные: [учитель, класс, подгруппа, предмет, количество занятий в неделю, аудитории]
data, class_groupings = ret()

# Максимальное время обработкии (float)
max_time = 90000.0
logs_on = True

# Временные слоты
days = range(1, 7)      # Дни с 1 по 5
periods = range(1,8)   # Пары с 1 по 6
time_slots = [(day, period) for day in days for period in periods]

# Модель
model = cp_model.CpModel()

# Подготовка наборов
teachers = set(entry[0] for entry in data)
classes = set(entry[1] for entry in data)
lessons = set(entry[3] for entry in data)
rooms = set(room for entry in data for room in entry[5])

# Привязка аудиторий к индексам
room_list = list(rooms)
room_indices = {room: idx for idx, room in enumerate(room_list)}

# Добавить виртуальные аудитории
virtual_rooms = []
for i in range(1, 5):
    virtual_rooms.append(f"Virtual_Room_{i}")
room_list.extend(virtual_rooms)
room_indices = {room: idx for idx, room in enumerate(room_list)}

# Добавить виртуальные аудитории в список доступных комнат для каждого урока
for entry in data:
    entry[5].extend(virtual_rooms)

# Переменные
x = {}
for entry in data:
    teacher, class_name, class_part, lesson, sessions_per_week, room_options = entry
    room_idxs = [room_indices[room] for room in room_options]
    for (day, period) in time_slots:
        for room_idx in room_idxs:
            key = (teacher, class_name, class_part, lesson, day, period, room_idx)
            x[key] = model.NewBoolVar(f"x_{teacher}_{class_name}_{class_part}_{lesson}_{day}_{period}_{room_list[room_idx]}")

# Ограничения

# 1. Учитель не может преподавать более одного урока одновременно
for teacher in teachers:
    for (day, period) in time_slots:
        teacher_vars = []
        for entry in data:
            if entry[0] == teacher:
                _, class_name, class_part, lesson, _, room_options = entry
                for room in room_options:
                    room_idx = room_indices[room]
                    key = (teacher, class_name, class_part, lesson, day, period, room_idx)
                    if key in x:
                        teacher_vars.append(x[key])
        if teacher_vars:
            model.Add(sum(teacher_vars) <= 1).WithName(f"TeacherAvailability_{teacher}_{day}_{period}")

# 2. Аудитория не может использоваться более одним уроком одновременно
for room_idx, room in enumerate(room_list):
    for (day, period) in time_slots:
        room_vars = []
        for entry in data:
            _, class_name, class_part, lesson, _, room_options = entry
            if room in room_options:
                teacher = entry[0]
                key = (teacher, class_name, class_part, lesson, day, period, room_idx)
                if key in x:
                    room_vars.append(x[key])
        if room_vars:
            model.Add(sum(room_vars) <= 1).WithName(f"RoomAvailability_{room}_{day}_{period}")

# 3. Каждый урок должен быть запланирован заданное количество раз в неделю
for entry in data:
    teacher, class_name, class_part, lesson, sessions_per_week, room_options = entry
    lesson_vars = []
    for (day, period) in time_slots:
        for room in room_options:
            room_idx = room_indices[room]
            key = (teacher, class_name, class_part, lesson, day, period, room_idx)
            if key in x:
                lesson_vars.append(x[key])
    model.Add(sum(lesson_vars) == sessions_per_week).WithName(f"LessonRequirement_{teacher}_{class_name}_{lesson}")

# 4. Каждый урок должнен быть назначен только в одну аудиторию
for entry in data:
    teacher, class_name, class_part, lesson, _, room_options = entry
    for (day, period) in time_slots:
        session_vars = []
        for room in room_options:
            room_idx = room_indices[room]
            key = (teacher, class_name, class_part, lesson, day, period, room_idx)
            if key in x:
                session_vars.append(x[key])
        if session_vars:
            model.Add(sum(session_vars) <= 1).WithName(f"OneRoomPerSession_{teacher}_{class_name}_{lesson}_{day}_{period}")

# 5. Подгруппы из одного списка могут иметь уроки одновременно
for class_name in classes:
    groupings = class_groupings.get(class_name, [])
    for group in groupings:
        for (day, period) in time_slots:
            group_vars = []
            for class_part in group:
                for entry in data:
                    if entry[1] == class_name and entry[2] == class_part:
                        teacher, _, lesson, _, room_options = entry[0], entry[2], entry[3], entry[4], entry[5]
                        for room in room_options:
                            room_idx = room_indices[room]
                            key = (teacher, class_name, class_part, lesson, day, period, room_idx)
                            if key in x:
                                group_vars.append(x[key])
            if group_vars:
                # Allow all subgroups in the group to have classes simultaneously
                model.Add(sum(group_vars) <= len(group)).WithName(f"GroupOverlap_{class_name}_Group_{'_'.join(group)}_{day}_{period}")
    
    # Проверка чтобы группы из разных списков не пересекались
    for (day, period) in time_slots:
        active_groupings = []
        for group in groupings:
            group_vars = []
            for class_part in group:
                for entry in data:
                    if entry[1] == class_name and entry[2] == class_part:
                        teacher, _, lesson, _, room_options = entry[0], entry[2], entry[3], entry[4], entry[5]
                        for room in room_options:
                            room_idx = room_indices[room]
                            key = (teacher, class_name, class_part, lesson, day, period, room_idx)
                            if key in x:
                                group_vars.append(x[key])
            if group_vars:
                group_active = model.NewBoolVar(f"GroupActive_{class_name}_Group_{'_'.join(group)}_{day}_{period}")
                model.AddMaxEquality(group_active, group_vars)
                active_groupings.append(group_active)
        if active_groupings:
            model.Add(sum(active_groupings) <= 1).WithName(f"NonOverlap_{class_name}_{day}_{period}")

    for class_name in classes:
        groupings = class_groupings.get(class_name, [])
        subgroups = set(part for group in groupings for part in group)
        for subgroup in subgroups:
            for (day, period) in time_slots:
                subgroup_vars = []
                for entry in data:
                    if entry[1] == class_name and entry[2] == subgroup:
                        teacher = entry[0]
                        lesson = entry[3]
                        room_options = entry[5]
                        for room in room_options:
                            room_idx = room_indices[room]
                            key = (teacher, class_name, subgroup, lesson, day, period, room_idx)
                            if key in x:
                                subgroup_vars.append(x[key])
                if subgroup_vars:
                    model.Add(sum(subgroup_vars) <= 1).WithName(f"SingleClass_{class_name}_{subgroup}_{day}_{period}")

# 6. Добавить веса для временных слотов и максимизировать количество свободных клеточек
time_slot_weights = {}
for day in days:
    for period in periods:
        # Ранние пары имеют меньший вес
        time_slot_weights[(day, period)] = period

# Создать список взвешенных переменных для уроков
weighted_vars = []
for key in x:
    teacher, class_name, class_part, lesson, day, period, room_idx = key
    weight = time_slot_weights[(day, period)]
    weighted_vars.append(x[key] * weight)

# Создать переменные для использования временных слотов
used = {}
for day in days:
    for period in periods:
        used[(day, period)] = model.NewBoolVar(f"used_{day}_{period}")
        # Если любая переменная x[key] в этот слот установлена, то used = 1
        lesson_vars = [x[key] for key in x if key[4] == day and key[5] == period]
        if lesson_vars:
            model.AddMaxEquality(used[(day, period)], lesson_vars)
        else:
            model.Add(used[(day, period)] == 0)
            
# Переменные, указывающие на использование виртуальных аудиторий
virtual_room_usage = []
for key in x:
    room_idx = key[6]
    room_name = room_list[room_idx]
    if room_name in virtual_rooms:
        virtual_room_usage.append(x[key])

# Минимизация количества окон у учителей
teacher_gap_vars = []
for teacher in teachers:
    for day in days:
        # Список занятости учителя по периодам в этот день
        busy = []
        for period in periods:
            # Переменная, указывающая, занят ли учитель в этот период
            is_busy = model.NewBoolVar(f"busy_{teacher}_{day}_{period}")
            lesson_vars = [x[key] for key in x if key[0] == teacher and key[4] == day and key[5] == period]
            if lesson_vars:
                model.AddMaxEquality(is_busy, lesson_vars)
            else:
                model.Add(is_busy == 0)
            busy.append(is_busy)
        # Вычислить количество переходов состояния занят/свободен
        transitions = []
        for p in range(len(busy) - 1):
            trans = model.NewBoolVar(f"trans_{teacher}_{day}_{p}")
            model.Add(trans == busy[p] != busy[p + 1])
            transitions.append(trans)
        total_transitions = model.NewIntVar(0, len(transitions), f"total_transitions_{teacher}_{day}")
        model.Add(total_transitions == sum(transitions))
        # Количество окон равно половине числа переходов
        num_gaps = model.NewIntVar(0, len(transitions), f"num_gaps_{teacher}_{day}")
        model.AddDivisionEquality(num_gaps, total_transitions, 2)
        teacher_gap_vars.append(num_gaps)

# Обновить целевую функцию для минимизации суммарного веса, использования временных слотов и количества окон
model.Minimize(5 * sum(weighted_vars) + 50 * sum(used.values()) + sum(teacher_gap_vars) + 1000 * sum(virtual_room_usage))

# Решатель
solver = cp_model.CpSolver()
solver.parameters.max_time_in_seconds = max_time # Лимит времени
solver.parameters.log_search_progress = logs_on   # Отключить логирование
solver.parameters.log_to_stdout = logs_on
status = solver.Solve(model)


if status == cp_model.OPTIMAL or status == cp_model.FEASIBLE:
    print("Решение найдено!")
    schedule = []
    for key in x:
        if solver.BooleanValue(x[key]):
            teacher, class_name, class_part, lesson, day, period, room_idx = key
            schedule.append({
                'Учитель': teacher,
                'Класс': class_name,
                'Подгруппа': class_part,
                'Предмет': lesson,
                'День': day,
                'Урок': period,
                'Аудитория': room_list[room_idx]
            })
    df_schedule = pd.DataFrame(schedule)
    df_schedule.sort_values(by=['День', 'Урок'], inplace=True)
    print(df_schedule)
    
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, Border, Side, PatternFill
    from openpyxl.utils import get_column_letter

    wb = Workbook()
    wb.remove(wb.active)

    def extract_class_number(name):
        parts = name.split('_')
        return int(parts[0]), int(parts[1])

    # Отсортировать названия классов
    class_names = sorted(df_schedule['Класс'].unique(), key=extract_class_number)

    # Имена дней недели
    days_names = {
        1: 'Понедельник',
        2: 'Вторник',
        3: 'Среда',
        4: 'Четверг',
        5: 'Пятница',
        6: 'Суббота'
    }

    subject_colors = [
        'FF6384',  # Красный
        '36A2EB',  # Синий
        'FFCE56',  # Желтый
        '4BC0C0',  # Бирюзовый
        '9966FF',  # Фиолетовый
        'FF9F40',  # Оранжевый
        '8B8B8B',  # Серый
        '00D084',  # Зеленый
        'C9CBCF',  # Светло-серый
        'FFCDFA',  # Розовый
        'FFD700',  # Золотой
        '40E0D0',  # Бирюза
        'ADFF2F',  # Желто-зеленый
        'FF69B4',  # Ярко-розовый
        'CD5C5C',  # Индийский красный
        '20B2AA',  # Светлый морской волны
        '87CEFA',  # Светло-голубой
        '778899',  # Светло-серый
        'B0C4DE',  # Светлая сталь
        '32CD32'   # Лайм
    ]

    subject_color_map = {}

    # Собрать уникальные предметы для назначения цветов
    subjects = df_schedule['Предмет'].unique()
    for idx, subject in enumerate(subjects):
        color = subject_colors[idx % len(subject_colors)]
        subject_color_map[subject] = color

    periods = range(1, 8)  # Пары с 1 по 7

    # Создание расписания для каждого класса
    for class_name in class_names:
        df_class = df_schedule[df_schedule['Класс'] == class_name]
        ws = wb.create_sheet(title=str(class_name))

        # Установить ширину столбцов
        for col in range(1, 8):
            ws.column_dimensions[get_column_letter(col)].width = 25

        # Заголовок листа
        ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=7)
        ws.cell(row=1, column=1).value = f"Расписание для класса {class_name}"
        ws.cell(row=1, column=1).alignment = Alignment(horizontal='center')
        ws.cell(row=1, column=1).font = Font(bold=True, size=16)

        # Заголовки дней недели
        for day in days_names:
            ws.cell(row=2, column=day + 1).value = days_names[day]
            ws.cell(row=2, column=day + 1).alignment = Alignment(horizontal='center')
            ws.cell(row=2, column=day + 1).font = Font(bold=True)
            ws.cell(row=2, column=day + 1).fill = PatternFill(start_color='BDD7EE', end_color='BDD7EE', fill_type='solid')

        # Номера уроков
        for period in periods:
            ws.cell(row=period + 2, column=1).value = f"Урок {period}"
            ws.cell(row=period + 2, column=1).alignment = Alignment(horizontal='center')
            ws.cell(row=period + 2, column=1).font = Font(bold=True)
            ws.cell(row=period + 2, column=1).fill = PatternFill(start_color='FFD966', end_color='FFD966', fill_type='solid')

        # Словарь расписания
        schedule_dict = {}
        for idx, row in df_class.iterrows():
            key = (row['День'], row['Урок'])
            value = {
                'text': f"{row['Предмет']} ({row['Аудитория']})\n{row['Учитель']}\n{row['Подгруппа']}",
                'subject': row['Предмет']
            }
            if key in schedule_dict:
                schedule_dict[key].append(value)
            else:
                schedule_dict[key] = [value]

        # Заполнение расписания
        for period in periods:
            for day in days_names:
                cell = ws.cell(row=period + 2, column=day + 1)
                key = (day, period)
                if key in schedule_dict:
                    cell_values = []
                    subjects_in_cell = set()
                    for entry in schedule_dict[key]:
                        text = entry['text']
                        subject = entry['subject']
                        cell_values.append(text)
                        subjects_in_cell.add(subject)
                    cell.value = "\n\n".join(cell_values)
                    cell.alignment = Alignment(vertical='top', wrap_text=True)
                    # Если в ячейке несколько предметов, оставляем белый фон
                    if len(subjects_in_cell) == 1:
                        subject = subjects_in_cell.pop()
                        fill_color = subject_color_map.get(subject, 'FFFFFF')
                        cell.fill = PatternFill(start_color=fill_color, end_color=fill_color, fill_type='solid')
                    else:
                        cell.fill = PatternFill(start_color='FFFFFF', end_color='FFFFFF', fill_type='solid')
                else:
                    cell.value = ""
                    cell.alignment = Alignment(vertical='top', wrap_text=True)

        # Границы таблицы
        thin_border = Border(left=Side(style='thin'),
                            right=Side(style='thin'),
                            top=Side(style='thin'),
                            bottom=Side(style='thin'))

        for row in ws.iter_rows(min_row=2, max_row=9, min_col=1, max_col=7):
            for cell in row:
                cell.border = thin_border

    # Создание расписания для каждого учителя
    teacher_names = df_schedule['Учитель'].unique()

    for teacher in teacher_names:
        df_teacher = df_schedule[df_schedule['Учитель'] == teacher]
        ws = wb.create_sheet(title=teacher[:31])  # Ограничение по длине имени листа в Excel

        # Установить ширину столбцов
        for col in range(1, 8):
            ws.column_dimensions[get_column_letter(col)].width = 25

        # Заголовок листа
        ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=7)
        ws.cell(row=1, column=1).value = f"Расписание для учителя {teacher}"
        ws.cell(row=1, column=1).alignment = Alignment(horizontal='center')
        ws.cell(row=1, column=1).font = Font(bold=True, size=16)

        # Заголовки дней недели
        for day in days_names:
            ws.cell(row=2, column=day + 1).value = days_names[day]
            ws.cell(row=2, column=day + 1).alignment = Alignment(horizontal='center')
            ws.cell(row=2, column=day + 1).font = Font(bold=True)
            ws.cell(row=2, column=day + 1).fill = PatternFill(start_color='BDD7EE', end_color='BDD7EE', fill_type='solid')

        # Номера уроков
        for period in periods:
            ws.cell(row=period + 2, column=1).value = f"Урок {period}"
            ws.cell(row=period + 2, column=1).alignment = Alignment(horizontal='center')
            ws.cell(row=period + 2, column=1).font = Font(bold=True)
            ws.cell(row=period + 2, column=1).fill = PatternFill(start_color='FFD966', end_color='FFD966', fill_type='solid')

        # Словарь расписания
        schedule_dict = {}
        for idx, row in df_teacher.iterrows():
            key = (row['День'], row['Урок'])
            value = {
                'text': f"{row['Предмет']} ({row['Аудитория']})\n{row['Класс']} ({row['Подгруппа']})",
                'subject': row['Предмет']
            }
            if key in schedule_dict:
                schedule_dict[key].append(value)
            else:
                schedule_dict[key] = [value]

        # Заполнение расписания
        for period in periods:
            for day in days_names:
                cell = ws.cell(row=period + 2, column=day + 1)
                key = (day, period)
                if key in schedule_dict:
                    cell_values = []
                    subjects_in_cell = set()
                    for entry in schedule_dict[key]:
                        text = entry['text']
                        subject = entry['subject']
                        cell_values.append(text)
                        subjects_in_cell.add(subject)
                    cell.value = "\n\n".join(cell_values)
                    cell.alignment = Alignment(vertical='top', wrap_text=True)
                    # Если в ячейке несколько предметов, оставляем белый фон
                    if len(subjects_in_cell) == 1:
                        subject = subjects_in_cell.pop()
                        fill_color = subject_color_map.get(subject, 'FFFFFF')
                        cell.fill = PatternFill(start_color=fill_color, end_color=fill_color, fill_type='solid')
                    else:
                        cell.fill = PatternFill(start_color='FFFFFF', end_color='FFFFFF', fill_type='solid')
                else:
                    cell.value = ""
                    cell.alignment = Alignment(vertical='top', wrap_text=True)

        # Границы таблицы
        thin_border = Border(left=Side(style='thin'),
                            right=Side(style='thin'),
                            top=Side(style='thin'),
                            bottom=Side(style='thin'))

        for row in ws.iter_rows(min_row=2, max_row=9, min_col=1, max_col=7):
            for cell in row:
                cell.border = thin_border

    # Сохранить книгу Excel
    output_filename = 'schedule_beautiful.xlsx'
    wb.save(output_filename)
    print(f"Данные успешно экспортированы в файл {output_filename}.")

else:
    print('Решения не найдены')