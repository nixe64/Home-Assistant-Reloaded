import memoizeOne from "memoize-one";
import { FrontendLocaleData } from "../../data/translation";
import { polyfillsLoaded } from "../translations/localize";

if (__BUILD__ === "latest" && polyfillsLoaded) {
  await polyfillsLoaded;
}

interface selectValueResult {
  value: number,
  unit: Intl.RelativeTimeFormatUnitSingular
}
const formatRelTimeMem = memoizeOne(
  (locale: FrontendLocaleData) =>
    // @ts-expect-error
    new Intl.RelativeTimeFormat(locale.language, { numeric: "auto" })
);

export const relativeTime = (
  from: Date,
  locale: FrontendLocaleData,
  to?: Date,
  includeTense = true
): string => {
  const diff = selectUnit(from, to);
  if (includeTense) {
    return formatRelTimeMem(locale).format(diff.value, diff.unit);
  }
  return Intl.NumberFormat(locale.language, {
    style: "unit",
    // @ts-expect-error
    unit: diff.unit,
    unitDisplay: "long",
  }).format(Math.abs(diff.value));
};

const MS_PER_SECOND = 1e3;
const SECS_PER_MIN = 60;
const SECS_PER_HOUR = SECS_PER_MIN * 60;
const SECS_PER_DAY = SECS_PER_HOUR * 24;
const SECS_PER_WEEK = SECS_PER_DAY * 7;
function selectUnit(from: Date, to?: Date, thresholds?) : selectValueResult {
    if (to === void 0) { to = new Date(); }
    if (thresholds === void 0) { thresholds = DEFAULT_THRESHOLDS; }
    var secs = (+from - +to) / MS_PER_SECOND;
    if (Math.abs(secs) < thresholds.second) {
        return {
            value: Math.round(secs),
            unit: 'second',
        };
    }
    var mins = secs / SECS_PER_MIN;
    if (Math.abs(mins) < thresholds.minute) {
        return {
            value: Math.round(mins),
            unit: 'minute',
        };
    }
    var hours = secs / SECS_PER_HOUR;
    if (Math.abs(hours) < thresholds.hour) {
        return {
            value: Math.round(hours),
            unit: 'hour',
        };
    }
    var days = secs / SECS_PER_DAY;
    if (Math.abs(days) < thresholds.day) {
        return {
            value: Math.round(days),
            unit: 'day',
        };
    }
    var fromDate = new Date(from);
    var toDate = new Date(to);
    var years = fromDate.getFullYear() - toDate.getFullYear();
    if (Math.round(Math.abs(years)) > 0) {
        return {
            value: Math.round(years),
            unit: 'year',
        };
    }
    var months = years * 12 + fromDate.getMonth() - toDate.getMonth();
    if (Math.round(Math.abs(months)) > 0) {
        return {
            value: Math.round(months),
            unit: 'month',
        };
    }
    var weeks = secs / SECS_PER_WEEK;
    return {
        value: Math.round(weeks),
        unit: 'week',
    };
}
const DEFAULT_THRESHOLDS = {
    second: 45,
    minute: 45,
    hour: 22,
    day: 5,
};
