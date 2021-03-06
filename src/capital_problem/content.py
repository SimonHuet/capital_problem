import dash_html_components
import pandas
from decouple import config
from pandas.io.parsers import read_csv
from pandas.io.sql import DatabaseError
import dashboard
import summary
import datetime
import numpy
import compute
import sys


def get_stacked_temperatures(dataframe: pandas.DataFrame, print_: bool = False):
    """Stack temperatures stored in multiple columns with days represented by rows

    Args:
        dataframe (pandas.DataFrame): Dataframe with columns as month and rows as days
        print_ (bool, optional): Print param to print the dataframe. Defaults to False.

    Returns:
        pandas.DataFrame: dataframe with temperatures stacked, a column for days and a column for months
    """

    # Stack temperature
    only_temperature = pandas.melt(
        dataframe,
        id_vars=[dataframe.columns[0]],
        value_vars=[
            dataframe.columns[index]
            for index in list(map(int, str(config("MONTH_COLUMNS")).split(",")))
        ],
        var_name="Month",
        value_name="Temperature",
    )

    if print_:
        print("stack\n", only_temperature)

    return only_temperature


def get_reference_spreadsheets(
    sheet_name: str, print_: bool = False
) -> pandas.DataFrame:
    """Get the reference spreadsheets

    Args:
        sheet_name (str, required) : Name of the sheet where to extract data.
        print_ (bool, optional): Print param to print the dataframe. Defaults to False.

    Returns:
        pandas.DataFrame: Reference spreadsheets
    """

    # Import XLSX
    reference_spreadsheets: pandas.DataFrame = pandas.read_excel(
        io=config("CLIMATE_PATH"),
        sheet_name=sheet_name,
        skiprows=int(config("CLIMATE_HEADER")) - 1,
        usecols=config("CLIMATE_COL_RANGE"),
    )

    # Select rows wich day on column 0 starting with 'Jn' where n is a number
    reference_spreadsheets = reference_spreadsheets[
        reference_spreadsheets.iloc[:, int(config("DAY_COL_INDEX"))].str.contains(
            "^J[0-9]+$"
        )
        == True
    ]

    # Put a trailling zero
    def pad_number(match):
        number = int(match.group(1))
        return format(number, "02d")

    reference_spreadsheets[
        reference_spreadsheets.columns[int(config("DAY_COL_INDEX"))]
    ] = reference_spreadsheets[
        reference_spreadsheets.columns[int(config("DAY_COL_INDEX"))]
    ].str.replace(
        r"^J([0-9]+)$", pad_number
    )

    # Replace month name by month locale's full name
    reference_spreadsheets.columns = header_month_convertor(
        reference_spreadsheets.columns.values
    )

    # Rename day column
    reference_spreadsheets.columns = header_column_rename(
        reference_spreadsheets.columns.values, "Day", int(config("DAY_COL_INDEX"))
    )

    if print_:
        print(reference_spreadsheets)

    return reference_spreadsheets


def get_all_capitals_spreadsheets(print_: bool = False) -> list:

    columns = str(config("ALL_CAPITALS_SPREADSHEETS_COLUMNS")).split(",")
    all_capitals_spreadsheets: pandas.DataFrame = pandas.read_csv(
        config("ALL_CAPITALS_SPREADSHEETS"),
        delimiter=",",
        usecols=columns,
    )

    # Rename columns
    all_capitals_spreadsheets.rename(
        columns={
            columns[0]: "Year",
            columns[1]: "Month",
            columns[2]: "Day",
            columns[3]: "Temperature",
            columns[4]: "Capital",
            columns[5]: "Region",
        },
        inplace=True,
    )

    # Filter on 2018
    all_capitals_spreadsheets = all_capitals_spreadsheets[
        all_capitals_spreadsheets["Year"] == 2018
    ]

    # Filter on Europe
    all_capitals_spreadsheets = all_capitals_spreadsheets[
        all_capitals_spreadsheets["Region"] == "Europe"
    ]
    # Filter on Capitals
    all_capitals_spreadsheets = all_capitals_spreadsheets[
        all_capitals_spreadsheets["Capital"].isin(
            str(config("CAPITALS_LIST")).split(";")
        )
    ]

    # Rename month
    all_capitals_spreadsheets["Month"] = all_capitals_spreadsheets["Month"].apply(
        lambda x: datetime.date(1900, x, 1).strftime("%B")
    )

    # Remove duplicates
    all_capitals_spreadsheets = all_capitals_spreadsheets.drop_duplicates(
        subset=["Year", "Month", "Day", "Capital"]
    )

    # Remove Unset temperatures (99F° according to the dataset)
    all_capitals_spreadsheets.loc[
        all_capitals_spreadsheets["Temperature"] <= -99, "Temperature"
    ] = numpy.nan

    # Split Dataframe on cities
    def map_dataframe(tuple_: tuple):
        # Remove outliers
        tuple_[1]["Temperature"] = remove_outliers(tuple_[1], "Temperature")

        # Transform temperatures from °F to °C
        tuple_[1]["Temperature"] = (tuple_[1]["Temperature"] - 32) * 5 / 9

        # Reset fuckedup index
        tuple_[1].reset_index(inplace=True)

        return (tuple_[1], tuple_[0])

    spreadsheets = list(
        map(
            map_dataframe,
            list(all_capitals_spreadsheets.groupby("Capital")),
        )
    )

    return spreadsheets


def remove_outliers(
    dataframe: pandas.DataFrame, column_outlier_name: str, print_: bool = False
) -> pandas.Series:
    # Detects outliers
    dataframe["mean"] = (
        dataframe[column_outlier_name]
        .rolling(window=5, center=True)
        .mean()
        .fillna(method="bfill")
        .fillna(method="ffill")
    )

    threshold = 10
    difference = numpy.abs(dataframe[column_outlier_name] - dataframe["mean"])
    outliers = difference > threshold

    if print_:
        print("outliers: ", dataframe[outliers][[column_outlier_name, "mean"]])

    if not outliers.empty:
        dataframe.loc[outliers, column_outlier_name] = numpy.nan
        dataframe[column_outlier_name] = dataframe[column_outlier_name].interpolate()

    return dataframe[column_outlier_name]


def get_alternate_spreadsheets(print_: bool = False) -> pandas.DataFrame:
    """Get the altenate spreadsheets

    Args:
        print_ (bool, optional): Print param to print the dataframe. Defaults to False.

    Returns:
        list: Reference spreadsheets
    """
    reference: list = str(config("SPREADSHEET_SAVUKOSKI")).split(";")
    spreadsheet: pandas.DataFrame = pandas.read_excel(
        io=reference[1], sheet_name=reference[2]
    )

    spreadsheet = spreadsheet.rename(
        columns={
            reference[3]: "Month",
            reference[4]: "Day",
            reference[5]: "Temperature",
        }
    )

    spreadsheet["Month"] = spreadsheet["Month"].apply(
        lambda x: datetime.date(1900, x, 1).strftime("%B")
    )

    if print_:
        print(spreadsheet)

    return (spreadsheet, reference[0])


def header_month_convertor(header_list: list):
    """Convert header month to locale's full name

    Args:
        header_list (list, required): header list param to convert the month.

    Returns:
        pandas.DataFrame: header list
    """
    for key, month_index in enumerate(
        list(map(int, str(config("MONTH_COLUMNS")).split(","))), start=1
    ):
        header_list[month_index] = datetime.date(1900, key, 1).strftime("%B")

    return header_list


def header_column_rename(header_list: list, column_name: str, column_index: int):
    """Rename column with a name

    Args:
        header_list (list, required): header list param to convert the month.
        column_name (str, required): New name for the column
        column_index (int, required): index of the column

    Returns:
        pandas.DataFrame: header list
    """
    header_list[column_index] = column_name

    return header_list


def create_date_column(year: pandas.Series, month: pandas.Series, day: pandas.Series):
    return pandas.to_datetime(
        year.astype(str) + "-" + month.astype(str) + "-" + day.astype(str),
        format="%Y-%B-%d",
        errors="coerce",
    )


def get_references_statistics(stacked_temperatures: dict, print_: bool = False):
    spreadsheets = get_all_capitals_spreadsheets(print_=print_)
    dtw_low, dtw_high = 0, -sys.maxsize - 1
    frechet_dist_low, frechet_dist_high = 0, -sys.maxsize - 1
    pcm_low, pcm_high = 0, -sys.maxsize - 1
    area_low, area_high = 0, -sys.maxsize - 1
    std_low, std_high = 0, -sys.maxsize - 1
    references = []

    for key, packed_spreadsheet in enumerate(spreadsheets, start=0):

        spreadsheet = packed_spreadsheet[0]
        name = packed_spreadsheet[1]

        spreadsheet["full_date"] = create_date_column(
            spreadsheet["Year"],
            spreadsheet["Month"],
            spreadsheet["Day"],
        )
        display_dataframe: pandas.DataFrame = pandas.concat(
            [
                spreadsheet["full_date"],
                stacked_temperatures[0]["Temperature"],
                stacked_temperatures[1]["Temperature"],
                spreadsheet["Temperature"],
            ],
            axis=1,
        )

        display_dataframe.columns = ["full_date", "SI", "SI-Erreur", name]

        stats_between_series = compute.stats_between_series(
            xaxis_1=stacked_temperatures[0]["full_date"],
            values_1=stacked_temperatures[0]["Temperature"],
            xaxis_2=spreadsheet["full_date"],
            values_2=spreadsheet["Temperature"],
        )

        dtw_low, dtw_high = min(stats_between_series.get("dtw"), dtw_low), max(
            dtw_high, stats_between_series.get("dtw")
        )
        frechet_dist_low, frechet_dist_high = (
            min(stats_between_series.get("frechet_dist"), frechet_dist_low),
            max(frechet_dist_high, stats_between_series.get("frechet_dist")),
        )
        pcm_low, pcm_high = min(stats_between_series.get("pcm"), pcm_low), max(
            pcm_high, stats_between_series.get("pcm")
        )
        area_low, area_high = min(stats_between_series.get("area"), area_low), max(
            area_high, stats_between_series.get("area")
        )
        std_low, std_high = min(stats_between_series.get("std"), std_low), max(
            std_high, stats_between_series.get("std")
        )

        visual_alternate_annual_graph = dashboard.build_time_series_chart(
            id="annual-graph-references-" + str(key),
            dates=display_dataframe["full_date"],
            data_list=[
                display_dataframe["SI"],
                display_dataframe["SI-Erreur"],
                display_dataframe[name],
            ],
            layout={
                "title": "Annual temperatures for " + name,
                "xaxis": {"title": "Date"},
                "yaxis": {"title": "Temperature in °C"},
                "dragmode": "pan",
            },
            all_=True,
        )

        visual_header = dash_html_components.H3(
            name, id="header-references-" + str(key)
        )

        references.append(
            {
                "visual_header": visual_header,
                "annual_graph": visual_alternate_annual_graph,
                "comparision_summary": None,
                "score": 0,
                "name": name,
                "stats_between_series": stats_between_series,
            }
        )

    for key, reference in enumerate(references, start=0):
        reference["score"] = numpy.abs(
            float(reference.get("stats_between_series").get("dtw") - dtw_low)
            / float(dtw_low - dtw_high)
            + float(reference.get("stats_between_series").get("pcm") - pcm_low)
            / float(pcm_low - pcm_high)
            + float(reference.get("stats_between_series").get("std") - std_low)
            / float(std_low - std_high)
        )

        reference["comparision_summary"] = dashboard.build_card_group(
            {
                **dict(reference.get("stats_between_series")),
                "Score": reference.get("score"),
            },
            "comparision-summary-references-" + str(key),
        )

        if print_:
            print("dataframe", reference.get("name"), ":", reference.get("score", 0))

    references.sort(key=lambda k: k["score"])
    return references[:5]


def get_savukoski_statistics(stacked_temperatures: dict, print_: bool = False):
    savukoski = get_alternate_spreadsheets(print_=print_)

    spreadsheet = savukoski[0]
    name = savukoski[1]

    spreadsheet["full_date"] = create_date_column(
        spreadsheet["Year"],
        spreadsheet["Month"],
        spreadsheet["Day"],
    )
    display_dataframe: pandas.DataFrame = pandas.concat(
        [
            spreadsheet["full_date"],
            stacked_temperatures[0]["Temperature"],
            stacked_temperatures[1]["Temperature"],
            spreadsheet["Temperature"],
        ],
        axis=1,
    )

    display_dataframe.columns = ["full_date", "SI", "SI-Erreur", name]

    stats_between_series = compute.stats_between_series(
        xaxis_1=stacked_temperatures[0]["full_date"],
        values_1=stacked_temperatures[0]["Temperature"],
        xaxis_2=spreadsheet["full_date"],
        values_2=spreadsheet["Temperature"],
    )

    visual_alternate_annual_graph = dashboard.build_time_series_chart(
        id="annual-graph-savukoski",
        dates=display_dataframe["full_date"],
        data_list=[
            display_dataframe["SI"],
            display_dataframe["SI-Erreur"],
            display_dataframe[name],
        ],
        layout={
            "title": "Annual temperatures for " + name,
            "xaxis": {"title": "Date"},
            "yaxis": {"title": "Temperature in °C"},
            "dragmode": "pan",
        },
        all_=True,
    )

    visual_alternate_comparision_summary = dashboard.build_card_group(
        stats_between_series, "comparision-summary-savukoski"
    )

    visual_header = dash_html_components.H2(
        "comparision with " + name + " for climate similarities", id="header-savukoski"
    )

    similarity_text = ""

    if stats_between_series.get("dtw", 0) < 100:
        similarity_text = (
            "the climate is similar to "
            + name
            + ". We should test capitals in a cold environnement"
        )
    elif stats_between_series.get("dtw", 0) < 200:
        similarity_text = (
            "the climate has similarities to "
            + name
            + ". We should test capitals in a cold or temperate environnement"
        )
    elif stats_between_series.get("dtw", 0) < 300:
        similarity_text = (
            "the climate is a bit different from " + name + ". It might be temperate"
        )
    else:
        similarity_text = (
            "the climate is different from "
            + name
            + ". We should test capitals not in a cold environnement"
        )

    visual_similarities = dash_html_components.P(
        "With a score of "
        + str(round(stats_between_series.get("dtw", 0), 2))
        + ", "
        + similarity_text,
    )
    if print_:
        print("dataframe", name, ":", stats_between_series.get("dtw", 0))

    return {
        "visual_header": visual_header,
        "annual_graph": visual_alternate_annual_graph,
        "comparision_summary": visual_alternate_comparision_summary,
        "similarities": visual_similarities,
        "score": stats_between_series.get("dtw", 0),
        "name": name,
    }


def get_statistics_dtw_proof(stacked_temperatures: dict, print_: bool = False):
    display_dataframe: pandas.DataFrame = pandas.concat(
        [
            stacked_temperatures[0]["full_date"],
            stacked_temperatures[0]["Temperature"],
            stacked_temperatures[1]["Temperature"],
        ],
        axis=1,
    )

    display_dataframe.columns = ["full_date", "SI", "SI-Erreur"]

    stats_between_series = compute.stats_between_series(
        xaxis_1=stacked_temperatures[0]["full_date"],
        values_1=stacked_temperatures[0]["Temperature"],
        xaxis_2=stacked_temperatures[1]["full_date"],
        values_2=stacked_temperatures[1]["Temperature"],
    )

    visual_alternate_annual_graph = dashboard.build_time_series_chart(
        id="annual-graph-dtw-proof",
        dates=display_dataframe["full_date"],
        data_list=[
            display_dataframe["SI"],
            display_dataframe["SI-Erreur"],
        ],
        layout={
            "title": "Annual temperatures for SI and SI-Erreur",
            "xaxis": {"title": "Date"},
            "yaxis": {"title": "Temperature in °C"},
            "dragmode": "pan",
        },
        all_=True,
    )

    visual_alternate_comparision_summary = dashboard.build_card_group(
        stats_between_series, "comparision-summary-dtw-proof"
    )

    visual_header = dash_html_components.H2(
        "Comparision between SI and SI-Erreur for dtw proof", id="header-dtw-proof"
    )

    similarity_text = ""

    if stats_between_series.get("dtw", 0) < 50:
        similarity_text = "the dtw statistic work for comparing two ordered datasets 🥳."
    else:
        similarity_text = "we should use an other comparative method."

    visual_similarities = dash_html_components.Div(
        children=[
            dash_html_components.P(
                "To test dtw effectiveness, we will test it on SI and SI-Error wich are very similar datasets. the result should state between 0 and 50. The more dtw is arround 0, the more similar datasets are",
            ),
            dash_html_components.P(
                "With a score of "
                + str(round(stats_between_series.get("dtw", 0), 2))
                + ", "
                + similarity_text,
            ),
        ],
    )
    if print_:
        print("dtw test :", stats_between_series.get("dtw", 0))

    return {
        "visual_header": visual_header,
        "annual_graph": visual_alternate_annual_graph,
        "comparision_summary": visual_alternate_comparision_summary,
        "similarities": visual_similarities,
    }


def get_statistics(sheet_name: str, print_: bool = False):
    # Get reference spreadsheets
    reference_spreadsheets = get_reference_spreadsheets(
        print_=print_, sheet_name=sheet_name
    )

    display_sheet_name = sheet_name.replace(" ", "").lower()

    if print_:
        print(display_sheet_name)

    # Stack all the temperatures with corresponding date
    stacked_temperatures = get_stacked_temperatures(
        reference_spreadsheets, print_=print_
    )
    # Create year column
    stacked_temperatures["Year"] = 2018
    stacked_temperatures["full_date"] = create_date_column(
        stacked_temperatures["Year"],
        stacked_temperatures["Month"],
        stacked_temperatures["Day"],
    )

    stacked_temperatures = stacked_temperatures[
        pandas.notna(stacked_temperatures["full_date"])
    ]

    stacked_temperatures["Temperature"] = pandas.to_numeric(
        stacked_temperatures["Temperature"], errors="coerce", downcast="float"
    ).interpolate()

    # Detects outliers
    sk_temp = stacked_temperatures

    sk_temp["mean"] = (
        stacked_temperatures["Temperature"]
        .rolling(window=5, center=True)
        .mean()
        .fillna(method="bfill")
        .fillna(method="ffill")
    )

    threshold = 10
    difference = numpy.abs(sk_temp["Temperature"] - sk_temp["mean"])
    outliers = difference > threshold

    if print_:
        print("outliers: ", sk_temp[outliers][["full_date", "Temperature", "mean"]])

    if not outliers.empty:
        stacked_temperatures.loc[outliers, "Temperature"] = numpy.nan
        stacked_temperatures["Temperature"] = stacked_temperatures[
            "Temperature"
        ].interpolate()

    # Unstack data
    months = stacked_temperatures["Month"].unique()

    spreadsheet_for_summary = stacked_temperatures[
        ["Day", "Month", "Temperature"]
    ].pivot(index=["Day"], columns="Month")

    spreadsheet_for_summary.columns = (
        spreadsheet_for_summary.columns.droplevel().rename(None)
    )

    spreadsheet_for_summary = spreadsheet_for_summary.reindex(months, axis=1)

    spreadsheet_for_summary.reset_index(level=0, inplace=True)

    # Make summary of month columns
    month_summary = summary.column_summary(
        dataframe=spreadsheet_for_summary.iloc[
            :, list(map(int, str(config("MONTH_COLUMNS")).split(",")))
        ],
        print_=print_,
        columns_meaning="Months",
    )

    # Make a year summary
    year_summary = summary.dataframe_summary(
        dataframe=spreadsheet_for_summary.iloc[
            :, list(map(int, str(config("MONTH_COLUMNS")).split(",")))
        ],
        print_=print_,
        dataframe_meaning="Year",
    )

    year_summary_without_meaning = year_summary
    year_summary_without_meaning.pop("dataframe_meaning", None)

    visual_year_summary = dashboard.build_card_group(
        year_summary_without_meaning, "year-cards"
    )
    visual_months_summary = dashboard.build_table_component(
        headers=month_summary.get("summary_headers", []),
        data=month_summary.get("summary_data", []),
        id="summary-table-" + display_sheet_name,
    )
    visual_monthly_graph = dashboard.build_time_series_chart(
        id="monthly-graph-" + display_sheet_name,
        dates=spreadsheet_for_summary["Day"],
        data_list=[
            spreadsheet_for_summary[column]
            for column in spreadsheet_for_summary.iloc[
                :, list(map(int, str(config("MONTH_COLUMNS")).split(",")))
            ]
        ],
        layout={
            "title": "Monthly temperatures",
            "xaxis": {"title": "Day"},
            "yaxis": {"title": "Temperature in °C"},
        },
    )
    visual_annual_graph = dashboard.build_time_series_chart(
        id="annual-graph-" + display_sheet_name,
        dates=stacked_temperatures["full_date"],
        data_list=[stacked_temperatures["Temperature"]],
        layout={
            "title": "Annual temperatures",
            "xaxis": {"title": "Date"},
            "yaxis": {"title": "Temperature in °C"},
            "dragmode": "pan",
        },
    )

    return {
        "month_summary": visual_months_summary,
        "year_summary": visual_year_summary,
        "monthly_graph": visual_monthly_graph,
        "annual_graph": visual_annual_graph,
        "stacked_temperatures": stacked_temperatures,
    }
