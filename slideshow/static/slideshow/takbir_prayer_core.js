(function (root, factory) {
    const api = factory();
    if (typeof module !== 'undefined' && module.exports) module.exports = api;
    root.TakbirPrayerCore = api;
}(typeof globalThis !== 'undefined' ? globalThis : this, function () {
    const METHODS = {
        karachi: {name: 'Karachi', fajr: 18, isha: 18},
        isna: {name: 'ISNA', fajr: 15, isha: 15},
        mwl: {name: 'Muslim World League', fajr: 18, isha: 17},
        ummalqura: {name: 'Umm al-Qura', fajr: 18.5, ishaMinutes: 90},
        egyptian: {name: 'Egyptian', fajr: 19.5, isha: 17.5}
    };
    const RAD = Math.PI / 180;
    const DAY_MS = 24 * 60 * 60 * 1000;

    function regionalMethod(latitude, longitude) {
        if (latitude >= 6 && latitude <= 38 && longitude >= 68 && longitude <= 98) return 'karachi';
        if (latitude >= 15 && latitude <= 72 && longitude >= -170 && longitude <= -50) return 'isna';
        if (latitude >= 16 && latitude <= 33 && longitude >= 34 && longitude <= 56) return 'ummalqura';
        if (latitude >= 20 && latitude <= 32 && longitude >= 24 && longitude <= 37) return 'egyptian';
        return 'mwl';
    }

    function dateParts(date, timeZone) {
        const parts = new Intl.DateTimeFormat('en-CA', {
            timeZone: timeZone,
            year: 'numeric',
            month: '2-digit',
            day: '2-digit'
        }).formatToParts(date);
        const values = {};
        parts.forEach(function (part) { values[part.type] = part.value; });
        return {year: Number(values.year), month: Number(values.month), day: Number(values.day)};
    }

    function minuteOfDay(date, timeZone) {
        const parts = new Intl.DateTimeFormat('en-GB', {
            timeZone: timeZone,
            hour: '2-digit',
            minute: '2-digit',
            hourCycle: 'h23'
        }).formatToParts(date);
        const values = {};
        parts.forEach(function (part) { values[part.type] = part.value; });
        return Number(values.hour) * 60 + Number(values.minute);
    }

    function zoneOffsetMinutes(year, month, day, timeZone) {
        const instant = new Date(Date.UTC(year, month - 1, day, 12));
        const parts = new Intl.DateTimeFormat('en-CA', {
            timeZone: timeZone,
            year: 'numeric',
            month: '2-digit',
            day: '2-digit',
            hour: '2-digit',
            minute: '2-digit',
            hourCycle: 'h23'
        }).formatToParts(instant);
        const values = {};
        parts.forEach(function (part) { values[part.type] = Number(part.value); });
        const zoneAsUtc = Date.UTC(values.year, values.month - 1, values.day, values.hour, values.minute);
        return (zoneAsUtc - instant.getTime()) / 60000;
    }

    function hijriMonth(year, month, day) {
        const date = new Date(Date.UTC(year, month - 1, day, 12));
        const options = {month: 'numeric', timeZone: 'UTC'};
        try {
            const parts = new Intl.DateTimeFormat('en-u-ca-islamic-umalqura-nu-latn', options)
                .formatToParts(date);
            return Number(parts.find(function (part) { return part.type === 'month'; }).value);
        } catch (error) {
            const parts = new Intl.DateTimeFormat('en-u-ca-islamic-nu-latn', options)
                .formatToParts(date);
            return Number(parts.find(function (part) { return part.type === 'month'; }).value);
        }
    }

    function solarCoordinates(date) {
        const start = Date.UTC(date.getUTCFullYear(), 0, 0);
        const dayOfYear = Math.floor((date.getTime() - start) / DAY_MS);
        const yearLength = new Date(Date.UTC(date.getUTCFullYear(), 1, 29)).getUTCDate() === 29 ? 366 : 365;
        const gamma = 2 * Math.PI / yearLength * (dayOfYear - 1);
        const equation = 229.18 * (
            0.000075 + 0.001868 * Math.cos(gamma) - 0.032077 * Math.sin(gamma)
            - 0.014615 * Math.cos(2 * gamma) - 0.040849 * Math.sin(2 * gamma)
        );
        const declination = 0.006918 - 0.399912 * Math.cos(gamma) + 0.070257 * Math.sin(gamma)
            - 0.006758 * Math.cos(2 * gamma) + 0.000907 * Math.sin(2 * gamma)
            - 0.002697 * Math.cos(3 * gamma) + 0.00148 * Math.sin(3 * gamma);
        return {equation: equation, declination: declination};
    }

    function hourAngle(altitude, latitude, declination) {
        const lat = latitude * RAD;
        const cosine = (Math.sin(altitude) - Math.sin(lat) * Math.sin(declination))
            / (Math.cos(lat) * Math.cos(declination));
        if (!Number.isFinite(cosine) || cosine < -1 || cosine > 1) return null;
        return Math.acos(cosine) / RAD;
    }

    function normalizeMinute(value) {
        return ((Math.round(value) % 1440) + 1440) % 1440;
    }

    function calculateDay(year, month, day, latitude, longitude, timeZone, methodKey) {
        const method = METHODS[methodKey] || METHODS[regionalMethod(latitude, longitude)];
        const date = new Date(Date.UTC(year, month - 1, day, 12));
        const solar = solarCoordinates(date);
        const offset = zoneOffsetMinutes(year, month, day, timeZone);
        const solarNoonUtc = 720 - 4 * longitude - solar.equation;
        const localNoon = solarNoonUtc + offset;
        const sunriseAngle = -0.833 * RAD;
        const sunriseHourAngle = hourAngle(sunriseAngle, latitude, solar.declination);
        if (sunriseHourAngle === null) return null;
        const sunrise = normalizeMinute(localNoon - sunriseHourAngle * 4);
        const sunset = normalizeMinute(localNoon + sunriseHourAngle * 4);
        const nightLength = (sunrise + 1440 - sunset) % 1440;
        const fajrHourAngle = hourAngle(-method.fajr * RAD, latitude, solar.declination);
        const fajr = fajrHourAngle === null
            ? normalizeMinute(sunrise - nightLength * method.fajr / 60)
            : normalizeMinute(localNoon - fajrHourAngle * 4);
        let isha;
        if (method.ishaMinutes) {
            const ishaMinutes = methodKey === 'ummalqura' && hijriMonth(year, month, day) === 9
                ? 120 : method.ishaMinutes;
            isha = normalizeMinute(sunset + ishaMinutes);
        } else {
            const ishaHourAngle = hourAngle(-method.isha * RAD, latitude, solar.declination);
            isha = ishaHourAngle === null
                ? normalizeMinute(sunset + nightLength * method.isha / 60)
                : normalizeMinute(localNoon + ishaHourAngle * 4);
        }

        function asr(factor) {
            const altitude = Math.atan(1 / (factor + Math.tan(Math.abs(latitude * RAD - solar.declination))));
            const angle = hourAngle(altitude, latitude, solar.declination);
            return angle === null ? null : normalizeMinute(localNoon + angle * 4);
        }

        return {
            date: year + '-' + String(month).padStart(2, '0') + '-' + String(day).padStart(2, '0'),
            method: method.name,
            fajr: fajr,
            sunrise: sunrise,
            ishraq: normalizeMinute(sunrise + 15),
            dhuhr: normalizeMinute(localNoon + 1),
            asrStandard: asr(1),
            asrHanafi: asr(2),
            maghrib: sunset,
            isha: isha
        };
    }

    function calculateYear(year, latitude, longitude, timeZone, methodKey) {
        const days = [];
        const count = new Date(Date.UTC(year, 1, 29)).getUTCDate() === 29 ? 366 : 365;
        for (let index = 0; index < count; index++) {
            const date = new Date(Date.UTC(year, 0, 1 + index, 12));
            const result = calculateDay(
                year, date.getUTCMonth() + 1, date.getUTCDate(),
                latitude, longitude, timeZone, methodKey
            );
            if (result) days.push(result);
        }
        return days;
    }

    function formatTime(minute) {
        if (minute === null || minute === undefined) return '--';
        const hour24 = Math.floor(minute / 60) % 24;
        const minutes = minute % 60;
        const suffix = hour24 >= 12 ? 'pm' : 'am';
        const hour12 = hour24 % 12 || 12;
        return hour12 + ':' + String(minutes).padStart(2, '0') + ' ' + suffix;
    }

    function hijriDate(year, month, day, adjustment) {
        const date = new Date(Date.UTC(year, month - 1, day + (adjustment || 0), 12));
        const options = {day: 'numeric', month: 'long', year: 'numeric', timeZone: 'UTC'};
        try {
            return new Intl.DateTimeFormat('en-u-ca-islamic-umalqura', options).format(date);
        } catch (error) {
            return new Intl.DateTimeFormat('en-u-ca-islamic', options).format(date);
        }
    }

    return {
        METHODS: METHODS,
        regionalMethod: regionalMethod,
        dateParts: dateParts,
        minuteOfDay: minuteOfDay,
        calculateDay: calculateDay,
        calculateYear: calculateYear,
        formatTime: formatTime,
        hijriDate: hijriDate
    };
}));
