# -*- coding: utf-8 -*-
"""
Created on Tue Mar 24 21:29:42 2020

@author: Denis Wolf
"""

from mip import Model, xsum, BINARY, INTEGER, OptimizationStatus
import pandas as pd
import datetime
import plotly.figure_factory as ff
import plotly.io as pio



# read input data from excel file (has multiple sheets)
def readData(filepath):
    
    data_employees = pd.read_excel(filepath,sheet_name="Employees").set_index("Name")
    demand = pd.read_excel(filepath,sheet_name="Demand").set_index("Day")
    parameters = pd.read_excel(filepath,sheet_name="Parameters").set_index("Parameter")
    input_days = pd.read_excel(filepath,sheet_name="Days").set_index("Day")
    optimization_parameters = pd.read_excel(filepath,sheet_name="Optimization_Parameters").set_index("Parameter")
            
    return data_employees, demand, parameters, input_days, optimization_parameters


# from a feasible solution, construct the workforce schedule as pandas dataframe
def generateSchedule(x,z,nr_employees, nr_days, nr_slots, list_employees, days, slots, input_days):
    column_names = ["Employee", "Date", "Day", "Start", "End"]

    rows = []

    for m in range(nr_employees):
        employee = list_employees[m]
        for t in range(nr_days):
            day = days[t]
        
            # type timestamp
            date = input_days.loc[day,"Date"]

            # convert timestamp to datetime
            date_datetime = pd.Timestamp(date).to_pydatetime()
            
            # each row in dataframe is represented in dictionary
            dic = {}
        
            start = None
            end = None
            
            for s in range(nr_slots):
                if z[m][t][s].x >= 0.99:
                    start = slots[s]
                if x[m][t][s].x >= 0.99:
                    end = slots[s]
                    
            dic["Employee"] = employee
            dic["Date"] = date_datetime
            dic["Day"] = day

            # check if employee works on given day
            if start is not None and end is not None:
                start = datetime.datetime(date_datetime.year, date_datetime.month, date_datetime.day, start.hour, start.minute)
                end = datetime.datetime(date_datetime.year, date_datetime.month, date_datetime.day, end.hour, end.minute) + datetime.timedelta(minutes=30)
                
            dic["Start"] = start
            dic["End"] = end
        
            rows.append(dic)

            
    plan = pd.DataFrame(rows, columns=column_names)
            
    return plan

# from a workforce schedule, construct a gantt chart using plotly
def getGantt(plan):
    
    df = plan.copy()
    df["Resource"] = df["Employee"]
    df = df.rename(columns = {"Employee" : "Task", "Start" : "Start", "End": "Finish"})

    step = (255 // (int(len(df["Resource"] ) ** (1 / 3))))
    colors = []

    for r in range(0, 256, step):
        for g in range(0, 256, step):
            for b in range(0, 256, step):
                colors.append(f'rgb({r}, {g}, {b})')
    
    fig = ff.create_gantt(df, colors,index_col='Resource', group_tasks=True, title = "Workforce schedule")
    return fig

# calculate weekly working times for the employees (including minus hours and overtime)
def calculateWorkingTimes(employees, plan, data_employees):
    
    workingTimes = dict.fromkeys(employees,0)
    

    for key, row in plan.iterrows():
        employee = row["Employee"]
        start = row["Start"]
        end = row["End"]
        if pd.isna(start):
            continue
        
        timeDiff = end - start
        hours = timeDiff.total_seconds() / 3600

        workingTimes[employee] += hours

    
    df_workingTimes = pd.DataFrame.from_dict(workingTimes, orient = "index", columns = ["WeeklyHours"]).rename_axis("Name")
    
    columns = ["Name", "min_hours_per_week", "max_hours_per_week"]
    df = df_workingTimes.merge(data_employees.filter(columns), left_index=True, right_index=True)
    
    df["minusHours"] = df["min_hours_per_week"] - df["WeeklyHours"]
    df["overtime"] = df["WeeklyHours"] - df["max_hours_per_week"]
    
    # minusHours and overTime can't be negative
    df[df < 0 ] = 0
    
    df = df[["min_hours_per_week", "max_hours_per_week", "WeeklyHours", "minusHours", "overtime"]]

    return df

# generate an excel file containing to sheets:
# Schedule: Start and end time of the employees' shifts
# weeklyHours: weekly working hours, minus hours and overtime per employee
def writeToExcel(plan, weeklyHours):
    
    plan_excel = plan.copy()
    
    plan_excel["Date"] = plan_excel["Date"].dt.strftime('%d.%m.%Y') 
    plan_excel["Start"] = plan_excel["Start"].dt.strftime("%H:%M")
    plan_excel["End"] = plan_excel["End"].dt.strftime("%H:%M")
    

    with pd.ExcelWriter("Solution.xlsx", engine='xlsxwriter') as writer:
    
        plan_excel.to_excel(writer, sheet_name="Schedule",index=False,float_format = "%0.1f")
        weeklyHours.to_excel(writer, sheet_name="weeklyHours", index=True)
    
        workbook  = writer.book
    
    
    
    
        # define green style
        green_format = workbook.add_format({'bg_color': '#0acd0a', 'font_color': '#ffffff'})
    
        # define red style
        red_format = workbook.add_format({'bg_color': '#f64d00', 'font_color': '#ffffff'})
    
        # sheet schedule
        worksheet_schedule = writer.sheets["Schedule"]
    
        # column width and format
        worksheet_schedule.set_column('B:B', 12)
        worksheet_schedule.set_column('C:C', 10)
        worksheet_schedule.set_column('D:F', 6)
    
    
        # sheet WweklyHours
        worksheet_weeklyHours = writer.sheets['weeklyHours']
    
        # column width
        worksheet_weeklyHours.set_column('A:A', 17)
        worksheet_weeklyHours.set_column('B:C', 18)
        worksheet_weeklyHours.set_column('D:F', 11)
    
        # conditional formats for minushours and overtime
        worksheet_weeklyHours.conditional_format('E2:E10000', {"type": "cell", "criteria": ">", "value": 0, "format": green_format})
        worksheet_weeklyHours.conditional_format('F2:F10000', {"type": "cell", "criteria": ">", "value": 0, "format": red_format})
        
        
        

input_datafile = "./data/InputData.xlsx"

data_employees, demand, parameters, input_days, optimization_parameters = readData(input_datafile)

list_employees = list(data_employees.index)
days = list(input_days.index)
slots = list(demand.columns)
    
nr_employees = len(list_employees)
nr_days = len(days)
nr_slots = len(slots)


if nr_employees == 0:
    raise Exception("Enter at least 1 employee!")
else:
    print("Input data read.")

print("Start scheduling.")

    
print("Build optimization model.")


# build optimization model
model = Model("Workforce_scheduling")

# boolean decision variable: x[m][t][s]: employee m works on day t during slot s
x = [[[model.add_var(name = "x_" + list_employees[m] + "_" + days[t] + "_" + str(slots[s]),var_type=BINARY) for s in range(nr_slots)] for t in range(nr_days)] for m in range(nr_employees)]

# boolean decision variable: z[m][t][s]: employee m starts working day on day t in slot s
z = [[[model.add_var(name = "z_" + list_employees[m] + "_" + days[t] + "_" + str(slots[s]),var_type=BINARY) for s in range(nr_slots)] for t in range(nr_days)] for m in range(nr_employees)]



model.objective = sum(x[m][t][s] for m in range(nr_employees) for t in range(nr_days) for s in range(nr_slots))

# constraint demand satisfaction: the demand for employees per slot must be met or exceeded
for t in range(nr_days):
    for s in range(nr_slots):
        constraint_name = "constraint_demand_" + days[t] + "_" + str(slots[s])
        
        # important to cast: pandas gives back numpy int64
        rhs = float(demand.loc[days[t], slots[s]])
        model += xsum(x[m][t][s] for m in range(nr_employees)) >= rhs, constraint_name
        
# optional constraint: the demand for employees with special qualification must be met or exceeded in each slot with demand
if parameters.loc["demand_specialQualification_per_Slot"]["to consider"] == "yes":
    for t in range(nr_days):
        for s in range(nr_slots):
            if demand.loc[days[t], slots[s]] > 0:
                constraint_name = "constraint_special_qualification_" + days[t] + "_" + str(slots[s])
                rhs = float(parameters.loc["demand_specialQualification_per_Slot"]["Value"])
                model += xsum(data_employees.loc[list_employees[m], "Special Qualification"] * x[m][t][s] for m in range(nr_employees)) >= rhs, constraint_name


# constraint only one start: if an employee works during a day his/her shift can only start once
for m in range(nr_employees):
    for t in range(nr_days):
        constraint_name = "constraint_one_start_" + list_employees[m] + "_" + days[t]
        model += xsum(z[m][t][s] for s in range(nr_slots)) <= 1, constraint_name

# optional constraint: max continue work days for each employee
if parameters.loc["max_employee_consecutive_working_days"]["to consider"] == "yes":
    max_continue_work_days=int(parameters.loc["max_employee_consecutive_working_days"]['Value'])
    for m in range(nr_employees):
        for t in range(max_continue_work_days, nr_days):
            constraint_name = "max_employee_consecutive_working_days_" + list_employees[m] + "_" + days[t]
            model += xsum(z[m][d][s]
                          for d in range(t-max_continue_work_days, t + 1)
                          for s in range(nr_slots)
                          ) <= max_continue_work_days, constraint_name

        
# constraint sequential shifts: a shift of an employee has to be consecutive
for m in range(nr_employees):
    for t in range(nr_days):
        for s in range(nr_slots):
            constraint_name = "constraint_sequential_shifts_" + list_employees[m] + "_" + days[t] + "_" + str(slots[s])
            if s == 0:
                model += z[m][t][s] >= x[m][t][s], constraint_name
            else:
                model += z[m][t][s] >= x[m][t][s] - x[m][t][s-1], constraint_name
            
# optional constraint: working time of employee can't exceed maximal allowed working time per day per employee
if parameters.loc["max_workingTime_per_Day"]["to consider"] == "yes": 
    for m in range(nr_employees):
        for t in range(nr_days):
            constraint_name = "constraint_maxWorkingTimeDay_" + list_employees[m] + "_" + days[t]
            rhs = float(parameters.loc["max_workingTime_per_Day"]["Value"]) * 2
            model += xsum(x[m][t][s] for s in range(nr_slots)) <= rhs, constraint_name
            
# optional constraint: if an employee works on a day, the shift has to be equal or longer than the minimal working time per day
if parameters.loc["min_workingTime_per_Day"]["to consider"] == "yes": 
    for m in range(nr_employees):
        for t in range(nr_days):
            constraint_name = "constraint_minWorkingTimeDay_" + list_employees[m] + "_" + days[t]
            rhs = 2 * float(parameters.loc["min_workingTime_per_Day"]["Value"]) * (xsum(z[m][t][s] for s in range(nr_slots)))
            model += xsum(x[m][t][s] for s in range(nr_slots)) >= rhs, constraint_name   


# optional constraint: each employee can only work a given amount of hours per week
if parameters.loc["max_hours_per_week"]["to consider"] == "yes":
    for m in range(nr_employees):
        hoursPerWeek = float(data_employees.loc[list_employees[m],"max_hours_per_week"]) 
        overtime = 0
        if parameters.loc["overtime_per_Week"]["to consider"] == "yes":
            overtime = float(parameters.loc["overtime_per_Week"]["Value"])
        
        constraint_name = "constraint_maxWorkingTimePerWeek_" + list_employees[m]
        model += xsum(x[m][t][s] for t in range(nr_days) for s in range(nr_slots)) <= (hoursPerWeek + overtime) * 2, constraint_name
        
# optional constraint: each employee has to work a given amount of hours per week
if parameters.loc["min_hours_per_week"]["to consider"] == "yes":
    for m in range(nr_employees):
        hoursPerWeek = float(data_employees.loc[list_employees[m],"min_hours_per_week"]) 
        minusHours = 0
        if parameters.loc["minusHours_per_Week"]["to consider"] == "yes":
            minusHours = float(parameters.loc["minusHours_per_Week"]["Value"])
        
        constraint_name = "constraint_minWorkingTimePerWeek_" + list_employees[m]
        model += xsum(x[m][t][s] for t in range(nr_days) for s in range(nr_slots)) >= (hoursPerWeek - minusHours) * 2, constraint_name


# optional constraint: each employee can only work a specific amount of hours on a given day (see data_employees). E.g. if this value is 0 then the employee can't work at all on this day
if parameters.loc["max_employee_WorkingTime_per_Day"]["to consider"] == "yes":
    for m in range(nr_employees):
        for t in range(nr_days):
            rhs = float(data_employees.loc[list_employees[m],days[t]])
            constraint_name = "constraint_maxHoursPerDay_Employee_" + list_employees[m] + "_" + days[t]
            model += xsum(x[m][t][s] for s in range(nr_slots)) <= rhs * 2, constraint_name



# special ordered set (SOS) type 1 for z variable:  at most one of the z variables can be set to one for each employee and day
# seems to slow down
# for m in range(nr_employees):
#     for t in range(nr_days):
#         model.add_sos([(z[m][t][s],1) for s in range(nr_slots)],1)

#model.write("model.lp")
            
# get nr of variables in model           
nrVariables = model.num_cols
# get nr of constraints in model
nrConstraints = model.num_rows

print("The mode consists of " + str(nrVariables) + " decision variables and " + str(nrConstraints) + " constraints.")

print("Optimization process started.")


# get time limit in seconds for optimization
timeInSeconds = optimization_parameters.loc["timeInSeconds","Value"]
# get mip gap
mipGap = optimization_parameters.loc["mipGap", "Value"]

# if time limit was given use this time limit else default value: +inf
if not pd.isna(timeInSeconds):
    model.max_seconds = timeInSeconds
    print("Maximal solution time: " + str(timeInSeconds) + " seconds")
   
# if mip gap was given use this gap else default value: 1e-4
if not pd.isna(mipGap):
    model.max_mip_gap = mipGap
    print("MIP gap set to " + str(mipGap * 100) + "%")


# start optimizing    
status = model.optimize()

solved = False

# optimal solution found
if status == OptimizationStatus.OPTIMAL:
    if model.gap < 1e-4:
        print("Optimal solution found.")
    else:
        print("Found a solution with gap <= set mip gap.")
        
    gap = round(model.gap * 100,3)
    print("Objective value: {}, gap: {}%".format(model.objective_value, gap))
    
    solved = True

# feasible solution found    
elif status == OptimizationStatus.FEASIBLE:
    print("Feasible solution found within time limit.")
    #print("Objective value: " + str(model.objective_value))
    gap = round(model.gap * 100,3)
    print("Objective value: {}, gap: {}%".format(model.objective_value, gap))
    
    solved = True

# problem instance is infeasible    
elif status == OptimizationStatus.INFEASIBLE:
    print("Problem instance not feasible.")
 
# error
else:
    print("ERROR!")
    print(status)

# if the instance was solved (optimal or feasible solution found), construct the workforce schedule for a week and visualize via gantt chart
if solved:
    print("Generate Gantt Chart.")
    plan = generateSchedule(x, z, nr_employees, nr_days, nr_slots, list_employees, days, slots, input_days)
    gantt = getGantt(plan)
    
    # show gantt chart in default browser
    pio.renderers.default='browser'
    #gantt.show()
    
    # create HTML file for gantt chart so that it can be deployed
    pio.write_html(gantt, file="index.html", auto_open=True)
    
    # generate solution as excel file
    weeklyTimes = calculateWorkingTimes(list_employees, plan, data_employees)
    writeToExcel(plan, weeklyTimes)
    
    






