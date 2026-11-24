(function () {
    'use strict';

    const tabs = Array.from(document.querySelectorAll('.takbir-tab'));
    if (!tabs.length || !window.TakbirPrayerCore) return;

    const Core = window.TakbirPrayerCore;
    const screens = {
        prayer: document.getElementById('prayer-screen'),
        mosques: document.getElementById('mosques-screen'),
        notifications: document.getElementById('notifications-screen'),
        website: document.getElementById('website-screen')
    };
    const PRAYER_CACHE_KEY = 'takbir_prayer_years_v1';
    const PRAYER_PREFS_KEY = 'takbir_prayer_prefs_v1';
    const ANNOUNCEMENTS_CACHE_KEY = 'takbir_announcements_v1';
    const TWENTY_KM_METERS = 20000;
    const ANNOUNCEMENTS_TTL_MS = 24 * 60 * 60 * 1000;
    const prayerLocation = document.getElementById('prayer-location');
    const prayerDate = document.getElementById('prayer-date');
    const prayerHijri = document.getElementById('prayer-hijri');
    const prayerList = document.getElementById('prayer-times-list');
    const nextName = document.getElementById('next-prayer-name');
    const nextTime = document.getElementById('next-prayer-time');
    const nextLabel = document.getElementById('next-prayer-label');
    const prayerDayPicker = document.getElementById('prayer-day-picker');
    const prayerMethodSummary = document.getElementById('prayer-method-summary');
    const websiteFrame = document.getElementById('website-frame');
    const methodSelect = document.getElementById('prayer-method');
    const hijriSelect = document.getElementById('hijri-adjustment');
    const notificationsList = document.getElementById('notifications-list');
    const notificationsUpdated = document.getElementById('notifications-updated');
    let activeTab = 'mosques';
    let prayerCaches = readJson(PRAYER_CACHE_KEY);
    if (!Array.isArray(prayerCaches)) prayerCaches = [];
    let prayerCache = null;
    let prayerPrefs = readJson(PRAYER_PREFS_KEY) || {method: 'auto', hijriAdjustment: 0};
    let prayerBusy = false;
    let notificationBusy = false;
    window.takbirActiveTab = activeTab;

    methodSelect.value = prayerPrefs.method || 'auto';
    hijriSelect.value = String(prayerPrefs.hijriAdjustment || 0);

    function readJson(key) {
        try {
            const value = localStorage.getItem(key);
            return value ? JSON.parse(value) : null;
        } catch (error) {
            console.warn('[Takbir] Could not read local cache:', key, error);
            return null;
        }
    }

    function saveJson(key, value) {
        try {
            localStorage.setItem(key, JSON.stringify(value));
            return true;
        } catch (error) {
            console.error('[Takbir] Could not save local cache:', key, error);
            return false;
        }
    }

    function setTab(tab) {
        activeTab = tab;
        window.takbirActiveTab = tab;
        const loader = document.getElementById('loader');
        if (loader) loader.style.display = 'none';
        const modal = document.getElementById('modal');
        if (modal) {
            modal.classList.remove('open');
            modal.setAttribute('aria-hidden', 'true');
        }
        tabs.forEach(function (button) {
            button.setAttribute('aria-selected', String(button.dataset.tab === tab));
        });
        Object.keys(screens).forEach(function (key) {
            screens[key].classList.toggle('active', key === tab);
        });
        if (tab === 'prayer') refreshPrayerTimes();
        if (tab === 'notifications') refreshAnnouncements();
        if (tab === 'website' && websiteFrame && !websiteFrame.hasAttribute('src')) {
            websiteFrame.src = websiteFrame.dataset.src;
        }
        if (tab === 'mosques') {
            setTimeout(function () {
                if (window.takbirLeafletMap) window.takbirLeafletMap.invalidateSize({pan: false});
            }, 80);
        }
    }

    tabs.forEach(function (button) {
        button.addEventListener('click', function () {
            setTab(button.dataset.tab);
        });
    });

    function getCurrentLocation() {
        return new Promise(function (resolve, reject) {
            if (!navigator.geolocation) {
                reject(new Error('Location is not available on this device.'));
                return;
            }
            navigator.geolocation.getCurrentPosition(
                function (position) {
                    resolve({
                        latitude: position.coords.latitude,
                        longitude: position.coords.longitude,
                        timeZone: Intl.DateTimeFormat().resolvedOptions().timeZone || 'UTC'
                    });
                },
                function () { reject(new Error('Location permission is needed to show local prayer times.')); },
                {enableHighAccuracy: false, timeout: 10000, maximumAge: 0}
            );
        });
    }

    async function getLocationName(location) {
        if (location.name) return location.name;
        try {
            const params = new URLSearchParams({
                latitude: location.latitude,
                longitude: location.longitude
            });
            const response = await fetch('/api/location-name/?' + params.toString(), {
                credentials: 'same-origin',
                cache: 'force-cache'
            });
            if (!response.ok) return '';
            const data = await response.json();
            return data.success && data.name ? data.name : '';
        } catch (error) {
            return '';
        }
    }

    function distanceMeters(a, b) {
        const toRad = function (degrees) { return degrees * Math.PI / 180; };
        const lat1 = toRad(a.latitude);
        const lat2 = toRad(b.latitude);
        const dLat = lat2 - lat1;
        const dLon = toRad(b.longitude - a.longitude);
        const h = Math.sin(dLat / 2) ** 2
            + Math.cos(lat1) * Math.cos(lat2) * Math.sin(dLon / 2) ** 2;
        return 6371000 * 2 * Math.atan2(Math.sqrt(h), Math.sqrt(1 - h));
    }

    function findPrayerCache(location, year, method) {
        return prayerCaches.find(function (cache) {
            return cache && cache.location && Array.isArray(cache.days)
                && cache.year === year
                && cache.methodPreference === method
                && cache.timeZone === location.timeZone
                && distanceMeters(cache.location, location) <= TWENTY_KM_METERS;
        }) || null;
    }

    function storePrayerCache(cache) {
        const sameSchedule = function (item) {
            return item && item.location && item.year === cache.year
                && item.methodPreference === cache.methodPreference
                && item.timeZone === cache.timeZone
                && distanceMeters(item.location, cache.location) < 1000;
        };
        prayerCaches = [cache].concat(prayerCaches.filter(function (item) {
            return !sameSchedule(item);
        })).slice(0, 3);
        saveJson(PRAYER_CACHE_KEY, prayerCaches);
    }

    function buildPrayerCache(location, year, methodPreference) {
        const method = methodPreference === 'auto'
            ? Core.regionalMethod(location.latitude, location.longitude)
            : methodPreference;
        prayerCache = {
            year: year,
            methodPreference: methodPreference,
            method: method,
            timeZone: location.timeZone,
            location: {
                latitude: location.latitude,
                longitude: location.longitude,
                name: location.name || prayerCache?.location?.name || ''
            },
            savedAt: Date.now(),
            days: Core.calculateYear(
                year, location.latitude, location.longitude, location.timeZone, method
            )
        };
        storePrayerCache(prayerCache);
    }

    async function refreshPrayerTimes() {
        if (prayerBusy) return;
        prayerBusy = true;
        prayerLocation.textContent = 'Checking your location…';
        try {
            let location;
            try {
                location = await getCurrentLocation();
            } catch (preciseLocationError) {
                const response = await fetch('/api/approx-location/', {
                    credentials: 'same-origin',
                    cache: 'no-store'
                });
                if (!response.ok) throw preciseLocationError;
                const approximate = await response.json();
                if (!approximate || !approximate.success
                    || !Number.isFinite(approximate.latitude)
                    || !Number.isFinite(approximate.longitude)) {
                    throw preciseLocationError;
                }
                location = {
                    latitude: approximate.latitude,
                    longitude: approximate.longitude,
                    timeZone: approximate.timezone
                        || Intl.DateTimeFormat().resolvedOptions().timeZone
                        || 'UTC',
                    approximate: true
                };
            }
            const date = Core.dateParts(new Date(), location.timeZone);
            const methodPreference = methodSelect.value || 'auto';
            prayerCache = findPrayerCache(location, date.year, methodPreference);
            if (!prayerCache) {
                buildPrayerCache(location, date.year, methodPreference);
            }
            prayerDayPicker.min = date.year + '-01-01';
            prayerDayPicker.max = date.year + '-12-31';
            prayerDayPicker.value = date.year + '-' + String(date.month).padStart(2, '0')
                + '-' + String(date.day).padStart(2, '0');
            const locationName = await getLocationName(location);
            if (locationName) {
                prayerCache.location.name = locationName;
                location.name = locationName;
                storePrayerCache(prayerCache);
            }
            prayerLocation.textContent = (location.approximate ? 'Approximate location · ' : 'Your location · ')
                + (locationName || prayerCache.location.name
                    || prayerCache.location.latitude.toFixed(2) + ', '
                        + prayerCache.location.longitude.toFixed(2));
            renderPrayerDay(date);
        } catch (error) {
            if (prayerCache && prayerCache.days) {
                const date = Core.dateParts(new Date(), prayerCache.timeZone);
                prayerDayPicker.min = date.year + '-01-01';
                prayerDayPicker.max = date.year + '-12-31';
                prayerLocation.textContent = 'Saved location · '
                    + (prayerCache.location.name
                        || prayerCache.location.latitude.toFixed(2) + ', '
                            + prayerCache.location.longitude.toFixed(2));
                renderPrayerDay(date);
            } else {
                prayerLocation.textContent = error.message;
                prayerDate.textContent = '';
                prayerHijri.textContent = '';
                prayerList.textContent = 'Allow location access to calculate prayer times for your area.';
                nextName.textContent = '--';
                nextTime.textContent = '--';
            }
        } finally {
            prayerBusy = false;
        }
    }

    function dayFor(date) {
        const key = date.year + '-' + String(date.month).padStart(2, '0')
            + '-' + String(date.day).padStart(2, '0');
        let day = prayerCache.days.find(function (item) { return item.date === key; });
        if (!day) {
            day = Core.calculateDay(
                date.year, date.month, date.day,
                prayerCache.location.latitude, prayerCache.location.longitude,
                prayerCache.timeZone, prayerCache.method
            );
        }
        return day;
    }

    function prayerRows(day) {
        return [
            ['Fajr', 'فجر', day.fajr, 'fajr'],
            ['Sunrise', 'طلوع آفتاب', day.sunrise, 'sunrise'],
            ['Ishraq', 'اشراق', day.ishraq, 'ishraq'],
            ['Dhuhr', 'ظہر', day.dhuhr, 'dhuhr'],
            ['Asr', 'عصر', day.asrStandard, 'asrStandard'],
            ['Asr (Hanafi)', 'عصر (حنفی)', day.asrHanafi, 'asrHanafi'],
            ['Maghrib', 'مغرب', day.maghrib, 'maghrib'],
            ['Sunset', 'غروب آفتاب', day.maghrib, 'sunset'],
            ['Isha', 'عشاء', day.isha, 'isha']
        ];
    }

    function renderPrayerDay(date) {
        const day = dayFor(date);
        if (!day) {
            prayerList.textContent = 'Prayer times are unavailable at this latitude for this date.';
            return;
        }
        const dateObject = new Date(Date.UTC(date.year, date.month - 1, date.day, 12));
        prayerDate.textContent = new Intl.DateTimeFormat(undefined, {
            weekday: 'long', month: 'long', day: 'numeric', year: 'numeric'
        }).format(dateObject);
        prayerHijri.textContent = Core.hijriDate(
            date.year, date.month, date.day, Number(hijriSelect.value || 0)
        );
        prayerMethodSummary.textContent = 'Calculation: ' + day.method;
        const now = new Date();
        const currentDate = Core.dateParts(now, prayerCache.timeZone);
        const isToday = currentDate.year === date.year
            && currentDate.month === date.month && currentDate.day === date.day;
        prayerDayPicker.value = date.year + '-' + String(date.month).padStart(2, '0')
            + '-' + String(date.day).padStart(2, '0');
        const currentMinute = Core.minuteOfDay(now, prayerCache.timeZone);
        const rows = prayerRows(day);
        let nextPrayer = rows.find(function (row) {
            return !['sunrise', 'sunset', 'ishraq'].includes(row[3])
                && row[2] !== null && (!isToday || row[2] > currentMinute);
        });
        if (!nextPrayer) {
            const tomorrow = new Date(Date.UTC(date.year, date.month - 1, date.day + 1, 12));
            const tomorrowDay = dayFor({
                year: tomorrow.getUTCFullYear(),
                month: tomorrow.getUTCMonth() + 1,
                day: tomorrow.getUTCDate()
            });
            nextPrayer = tomorrowDay
                ? ['Fajr', 'فجر', tomorrowDay.fajr, 'fajr']
                : rows[0];
        }
        nextLabel.textContent = isToday ? 'Next prayer' : 'First prayer';
        nextName.textContent = nextPrayer[0] + ' · ' + nextPrayer[1];
        nextTime.textContent = 'At ' + Core.formatTime(nextPrayer[2]);
        prayerList.replaceChildren();
        rows.forEach(function (row) {
            const element = document.createElement('div');
            element.className = 'prayer-time-row' + (row === nextPrayer ? ' is-next' : '');
            if (row[3] === 'sunrise' || row[3] === 'sunset') {
                element.classList.add('blue');
            }
            const label = document.createElement('strong');
            label.textContent = row[0];
            const urdu = document.createElement('span');
            urdu.className = 'prayer-urdu';
            urdu.textContent = row[1];
            const value = document.createElement('time');
            value.textContent = Core.formatTime(row[2]);
            element.append(label, urdu, value);
            prayerList.appendChild(element);
        });
    }

    methodSelect.addEventListener('change', function () {
        prayerPrefs.method = methodSelect.value;
        saveJson(PRAYER_PREFS_KEY, prayerPrefs);
        if (prayerCache) {
            buildPrayerCache(prayerCache.location, prayerCache.year, methodSelect.value);
            const selected = prayerDayPicker.value.split('-').map(Number);
            renderPrayerDay(selected.length === 3
                ? {year: selected[0], month: selected[1], day: selected[2]}
                : Core.dateParts(new Date(), prayerCache.timeZone));
        }
    });

    hijriSelect.addEventListener('change', function () {
        prayerPrefs.hijriAdjustment = Number(hijriSelect.value);
        saveJson(PRAYER_PREFS_KEY, prayerPrefs);
        if (prayerCache) {
            const selected = prayerDayPicker.value.split('-').map(Number);
            renderPrayerDay(selected.length === 3
                ? {year: selected[0], month: selected[1], day: selected[2]}
                : Core.dateParts(new Date(), prayerCache.timeZone));
        }
    });

    prayerDayPicker.addEventListener('change', function () {
        const selected = prayerDayPicker.value.split('-').map(Number);
        if (selected.length === 3 && prayerCache && selected[0] === prayerCache.year) {
            renderPrayerDay({year: selected[0], month: selected[1], day: selected[2]});
        } else if (prayerCache) {
            prayerDayPicker.value = prayerCache.year + '-01-01';
        }
    });

    function renderAnnouncements(items) {
        notificationsList.replaceChildren();
        if (!items.length) {
            const empty = document.createElement('div');
            empty.className = 'notification-empty';
            empty.textContent = 'There are no announcements yet.';
            notificationsList.appendChild(empty);
            return;
        }
        items.forEach(function (item) {
            const card = document.createElement('article');
            card.className = 'announcement-card';
            const title = document.createElement('h2');
            title.textContent = item.title;
            const meta = document.createElement('div');
            meta.className = 'announcement-meta';
            const published = new Date(item.published_at);
            meta.textContent = Number.isNaN(published.getTime())
                ? '' : published.toLocaleDateString(undefined, {year: 'numeric', month: 'short', day: 'numeric'});
            const body = document.createElement('p');
            body.textContent = item.body;
            card.append(title, meta, body);
            if (item.source) {
                const source = document.createElement('p');
                source.className = 'announcement-source';
                source.textContent = 'Source: ' + item.source;
                card.appendChild(source);
            }
            notificationsList.appendChild(card);
        });
    }

    async function refreshAnnouncements() {
        if (notificationBusy) return;
        const cached = readJson(ANNOUNCEMENTS_CACHE_KEY);
        if (cached && Array.isArray(cached.announcements)) {
            renderAnnouncements(cached.announcements);
            if (Date.now() - cached.savedAt < ANNOUNCEMENTS_TTL_MS) {
                notificationsUpdated.textContent = 'Updated '
                    + new Date(cached.savedAt).toLocaleString() + '.';
                return;
            }
        }

        notificationBusy = true;
        notificationsUpdated.textContent = 'Checking for announcements…';
        try {
            const response = await fetch('/api/public/announcements/', {
                cache: 'no-store',
                credentials: 'same-origin'
            });
            if (!response.ok) throw new Error('Announcements could not be loaded.');
            const data = await response.json();
            if (!data.success || !Array.isArray(data.announcements)) {
                throw new Error('The announcements response was invalid.');
            }
            const nextCache = {savedAt: Date.now(), announcements: data.announcements};
            saveJson(ANNOUNCEMENTS_CACHE_KEY, nextCache);
            renderAnnouncements(nextCache.announcements);
            notificationsUpdated.textContent = 'Updated just now.';
        } catch (error) {
            notificationsUpdated.textContent = cached
                ? 'Could not refresh; showing saved announcements.'
                : error.message;
            if (!cached) renderAnnouncements([]);
        } finally {
            notificationBusy = false;
        }
    }
}());
