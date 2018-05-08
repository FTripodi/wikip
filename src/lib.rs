extern crate chrono;
#[macro_use]
extern crate failure;
extern crate log;

use chrono::prelude::*;
use chrono::Duration;
use failure::Error;
use std::path::PathBuf;

pub struct DateOptions {
    pub date: Date<Local>,
    pub duration: Option<Duration>,
    pub week: Option<u8>,
}

pub struct Options {
    pub date_options: DateOptions,
    pub log_level: log::Level,
    pub output: Option<PathBuf>,
}

pub fn execute(options: Options) -> Result<(), Error> {
    unimplemented!()
}

#[cfg(test)]
mod test {
    #[test]
    fn test() {
        assert!(true)
    }
}
