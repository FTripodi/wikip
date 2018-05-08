#![feature(transpose_result)]

extern crate chrono;
#[macro_use]
extern crate clap;
#[macro_use]
extern crate failure;
extern crate log;
extern crate simple_logging;
extern crate wikip;

use chrono::prelude::*;
use clap::Arg;
use failure::Error;
use std::path::PathBuf;
use wikip::{execute, DateOptions, Options};

fn main() {
    let options = parse_args().unwrap();
    execute(options).unwrap();
}

fn parse_args<'a>() -> Result<Options, Error> {
    let matches = app_from_crate!()
        .arg(
            Arg::with_name("date")
                .value_name("DATE")
                .short("d")
                .long("date")
                .takes_value(true)
                .help("The date to get the AfD's for.")
                .long_help(
                    "The date to get the AfD's for. Defaults to everything listed on the AfD \
                     page. The format is YYYY-MM-DD.",
                ),
        )
        .arg(
            Arg::with_name("date_range")
                .value_name("DATE_RANGE")
                .short("r")
                .long("date-range")
                .takes_value(true)
                .help("An inclusive range of dates to scrape.")
                .long_help(
                    "An inclusive range of dates to scrape. The format is YYYY-MM-DD/YYYY-MM-DD",
                ),
        )
        .arg(
            Arg::with_name("week")
            .value_name("WEEK")
            .short("w")
            .long("week")
                .takes_value(true)
            .help("Generate reports only for a particular week of the month.")
            .long_help("Generate reports only for a particular week of the month. 0 is the first \
            week, 1 is the first full week of the month. Ommitting this processes all days. \
            This only applies in conjunction with either DATE or DATE_RANGE.")
            )
        .arg(
            Arg::with_name("level")
            .value_name("LOG_LEVEL")
            .short("l")
            .long("level")
                .takes_value(true)
            .default_value("Warn")
            .possible_values(&["Error", "Warn", "Info", "Debug", "Trace"])
            )
        .arg(
            Arg::with_name("output")
            .value_name("FILENAME")
            .short("o")
            .long("output")
                .takes_value(true)
            .required(false)
            .help("The output file.")
            .long_help("THe output file. It defaults to 'afd-bios-DATE.csv'.")
            )
        .get_matches();

    let start_date: Date<Local> = matches
        .value_of("date")
        .or_else(|| {
            matches
                .value_of("date_range")
                .and_then(|dr| dr.split('/').next())
        })
        .map(|date_str| date_str.parse().map(|dt: DateTime<Local>| dt.date()))
        .transpose()
        .map_err(|err| format_err!("Error reading DATE: {}", &err))?
        .unwrap_or_else(|| Local::now().date());
    let end_date: Option<Date<Local>> = matches
        .value_of("date_range")
        .and_then(|dr| dr.split('/').nth(1))
        .map(|date_str| date_str.parse().map(|dt: DateTime<Local>| dt.date()))
        .transpose()
        .map_err(|err| format_err!("Error reading DATE_RANGE: {}", &err))?;
    let week: Option<u8> = matches
        .value_of("date")
        .or_else(|| matches.value_of("date_range"))
        .and_then(|_| matches.value_of("week"))
        .map(|w| w.parse())
        .transpose()
        .map_err(|err| format_err!("Error reading WEEK: {}", &err))?;
    let log_level: log::Level = matches
        .value_of("level")
        .unwrap_or("Warn")
        .parse()
        .map_err(|err| format_err!("Error reading LEVEL: {}", &err))?;
    let output: Option<PathBuf> = matches
        .value_of("output")
        .map(|o| o.parse())
        .transpose()
        .map_err(|err| format_err!("Error reading OUTPUT: {}", &err))?;

    Ok(Options {
        date_options: DateOptions {
            date: start_date,
            duration: end_date.map(|ed| ed - start_date),
            week,
        },
        log_level,
        output,
    })
}
