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
    const DAILY_CONTENT_CACHE_KEY = 'takbir_quran_package_v1';
    const REGIONAL_LOCATION_CACHE_KEY = 'takbir_regional_location_v1';
    const prayerLabels = JSON.parse(document.getElementById('takbir-prayer-labels').textContent);
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
    let prayerCache = prayerCaches.find(cache => cache && cache.location && Array.isArray(cache.days)) || null;
    let prayerPrefs = readJson(PRAYER_PREFS_KEY) || {method: 'auto', hijriAdjustment: 0};
    let prayerBusy = false;
    let notificationBusy = false;
    let dailyContentBusy = false;
    let dailyContentPackage = null;
    let currentAnnouncements = [];
    let regionalLocation = readJson(REGIONAL_LOCATION_CACHE_KEY);
    let locationPromise = null;
    let regionRequest = 0;
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
        if (tab === 'notifications') {
            refreshAnnouncements();
            refreshDailyContent();
            refreshNotificationLocation();
        }
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

    function getDeviceLocation() {
        if (!locationPromise) {
            locationPromise = (async function () {
                try {
                    return await getCurrentLocation();
                } catch (preciseLocationError) {
                    const response = await fetch('/api/approx-location/', {
                        credentials: 'same-origin', cache: 'no-store'
                    });
                    if (!response.ok) throw preciseLocationError;
                    const approximate = await response.json();
                    if (!approximate || !approximate.success
                        || !Number.isFinite(approximate.latitude)
                        || !Number.isFinite(approximate.longitude)) {
                        throw preciseLocationError;
                    }
                    return {
                        latitude: approximate.latitude, longitude: approximate.longitude,
                        timeZone: approximate.timezone
                            || Intl.DateTimeFormat().resolvedOptions().timeZone || 'UTC',
                        approximate: true
                    };
                }
            }()).finally(function () { locationPromise = null; });
        }
        return locationPromise;
    }

    function regionalLanguage() {
        return regionalLocation?.language || 'ur';
    }

    async function updateRegionalLocation(location) {
        const requestId = ++regionRequest;
        const previous = regionalLocation;
        if (previous && distanceMeters(previous, location) > 1000) {
            regionalLocation = null;
            saveJson(REGIONAL_LOCATION_CACHE_KEY, null);
            renderAnnouncements(currentAnnouncements);
        }
        try {
            const params = new URLSearchParams({
                latitude: location.latitude,
                longitude: location.longitude,
                regional: '1'
            });
            const response = await fetch('/api/location-name/?' + params.toString(), {
                credentials: 'same-origin',
                cache: 'force-cache'
            });
            if (!response.ok) throw new Error('Location lookup failed: ' + response.status);
            const data = await response.json();
            if (!data.success) throw new Error('Location lookup failed.');
            if (requestId !== regionRequest) return '';
            regionalLocation = {
                latitude: location.latitude, longitude: location.longitude,
                language: data.regional_language || '', name: data.name || ''
            };
            saveJson(REGIONAL_LOCATION_CACHE_KEY, regionalLocation);
            renderAnnouncements(currentAnnouncements);
            if (prayerCache && prayerDayPicker.value) {
                const selected = prayerDayPicker.value.split('-').map(Number);
                if (selected.length === 3) {
                    renderPrayerDay({year: selected[0], month: selected[1], day: selected[2]});
                }
            }
            return regionalLocation.name;
        } catch (error) {
            console.warn('[Takbir] Could not resolve regional language:', error);
            return '';
        }
    }

    async function refreshNotificationLocation() {
        try {
            const location = await getDeviceLocation();
            await updateRegionalLocation(location);
        } catch (error) {
            console.warn('[Takbir] Could not update announcement location:', error);
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
            const location = await getDeviceLocation();
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
            const locationName = await updateRegionalLocation(location);
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
        const language = regionalLanguage();
        const labels = prayerLabels[language] || prayerLabels.ur;
        const extra = {
            gu: {ishraq: 'ઇશરાક', hanafi: 'હનફી'},
            ur: {ishraq: 'اشراق', hanafi: 'حنفی'}
        }[language] || {ishraq: 'Ishraq', hanafi: 'Hanafi'};
        return [
            ['Fajr', labels.fajr, day.fajr, 'fajr'],
            ['Sunrise', labels.sunrise, day.sunrise, 'sunrise'],
            ['Ishraq', extra.ishraq, day.ishraq, 'ishraq'],
            ['Dhuhr', labels.dhuhr, day.dhuhr, 'dhuhr'],
            ['Asr', labels.asr, day.asrStandard, 'asrStandard'],
            ['Asr (Hanafi)', labels.asr + ' (' + extra.hanafi + ')', day.asrHanafi, 'asrHanafi'],
            ['Maghrib', labels.maghrib, day.maghrib, 'maghrib'],
            ['Sunset', labels.sunset, day.maghrib, 'sunset'],
            ['Isha', labels.isha, day.isha, 'isha']
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
            nextPrayer = tomorrowDay ? prayerRows(tomorrowDay)[0] : rows[0];
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
            label.style.whiteSpace = 'nowrap';
            const regional = document.createElement('span');
            regional.className = 'prayer-regional';
            regional.lang = regionalLanguage();
            regional.dir = ['ur', 'ks', 'sd'].includes(regionalLanguage()) ? 'rtl' : 'ltr';
            regional.textContent = row[1];
            const value = document.createElement('time');
            value.textContent = Core.formatTime(row[2]);
            element.append(label, value, regional);
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
        currentAnnouncements = Array.isArray(items) ? items : [];
        const dailyContentCard = createDailyContentCard(dailyContentPackage);
        if (dailyContentCard) notificationsList.appendChild(dailyContentCard);
        if (!currentAnnouncements.length) {
            if (dailyContentCard) return;
            const empty = document.createElement('div');
            empty.className = 'notification-empty';
            empty.textContent = 'There are no announcements yet.';
            notificationsList.appendChild(empty);
            return;
        }
        function appendLinkedText(element, text) {
            const urlPattern = /https?:\/\/[^\s<>"']+/gi;
            let lastIndex = 0;
            let match;
            while ((match = urlPattern.exec(text)) !== null) {
                let url = match[0];
                while (/[.,!?;:]$/.test(url)) url = url.slice(0, -1);
                if (!url) continue;

                element.appendChild(document.createTextNode(text.slice(lastIndex, match.index)));
                const link = document.createElement('a');
                link.href = url;
                link.target = '_blank';
                link.rel = 'noopener noreferrer';
                link.textContent = url;
                element.appendChild(link);
                lastIndex = match.index + url.length;
                urlPattern.lastIndex = lastIndex;
            }
            element.appendChild(document.createTextNode(text.slice(lastIndex)));
        }

        currentAnnouncements.forEach(function (item) {
            const card = document.createElement('article');
            card.className = 'announcement-card';
            const title = document.createElement('h2');
            title.className = 'announcement-text';
            title.dir = 'auto';
            title.textContent = item.title;
            const meta = document.createElement('div');
            meta.className = 'announcement-meta';
            const published = new Date(item.published_at);
            meta.textContent = Number.isNaN(published.getTime())
                ? '' : published.toLocaleDateString(undefined, {year: 'numeric', month: 'short', day: 'numeric'});
            const body = document.createElement('p');
            body.className = 'announcement-text';
            body.dir = 'auto';
            appendLinkedText(body, item.body);
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

    function createDailyContentCard(packageData) {
        const approved = packageData && Array.isArray(packageData.entries)
            ? packageData.entries.map(normalizeDailyContentEntry).filter(entry =>
                ['quran', 'hadith'].includes(entry.type)
                && entry.review_status === 'approved' && entry.translations)
            : [];
        if (!approved.length) return null;

        const now = new Date();
        const dateText = [
            now.getFullYear(),
            String(now.getMonth() + 1).padStart(2, '0'),
            String(now.getDate()).padStart(2, '0')
        ].join('-');
        const startOfYear = Date.UTC(now.getFullYear(), 0, 1);
        const today = Date.UTC(now.getFullYear(), now.getMonth(), now.getDate());
        const dayOfYear = Math.floor((today - startOfYear) / 86400000);
        const entry = approved[dayOfYear % approved.length];
        const citation = entry.citation || {};
        const citationText = entry.type === 'quran'
            ? `Surah ${citation.surah || ''} · Chapter ${citation.chapter || ''} · Verse ${citation.verse || ''}`
            : `${citation.book || 'Hadith collection'} · Hadith ${citation.number || ''}`;
        const card = document.createElement('article');
        card.className = 'announcement-card daily-content-card';
        card.dataset.dailyContent = dateText;

        const arabic = document.createElement('p');
        arabic.className = 'announcement-text';
        arabic.lang = 'ar';
        arabic.dir = 'rtl';
        arabic.textContent = entry.arabic || '';
        card.appendChild(arabic);

        const english = document.createElement('p');
        english.className = 'announcement-text';
        english.dir = 'auto';
        english.textContent = entry.translations.en || '';
        card.appendChild(english);

        const languageCode = regionalLocation?.language
            || (navigator.language || 'en').split('-')[0].toLowerCase();
        const regional = entry.translations[languageCode];
        if (languageCode !== 'en' && regional) {
            const regionalText = document.createElement('p');
            regionalText.className = 'announcement-text';
            regionalText.lang = languageCode;
            regionalText.dir = ['ur', 'ks', 'sd'].includes(languageCode) ? 'rtl' : 'auto';
            regionalText.textContent = regional;
            card.appendChild(regionalText);
        } else if (languageCode === 'gu') {
            const unavailable = document.createElement('p');
            unavailable.className = 'announcement-source';
            unavailable.textContent = 'Gujarati translation is not yet available.';
            card.appendChild(unavailable);
        }

        if (entry.type === 'quran') {
            const sourceInfo = packageData.arabic_source || {};
            const details = document.createElement('details');
            const summary = document.createElement('summary');
            summary.textContent = 'License information';
            details.append(summary, document.createTextNode(sourceInfo.copyright_notice || ''));
            const license = document.createElement('a');
            license.href = 'https://creativecommons.org/licenses/by/3.0/';
            license.target = '_blank';
            license.rel = 'noopener noreferrer';
            license.textContent = 'CC BY 3.0 license';
            details.append(document.createTextNode(' · '), license);
            card.appendChild(details);
        }

        const citationFooter = document.createElement('p');
        citationFooter.className = 'daily-citation';
        citationFooter.textContent = citationText;
        card.appendChild(citationFooter);
        if (entry.type === 'quran' && packageData.arabic_source?.url) {
            const source = document.createElement('p');
            source.className = 'daily-source';
            const link = document.createElement('a');
            link.href = packageData.arabic_source.url;
            link.target = '_blank';
            link.rel = 'noopener noreferrer';
            link.textContent = 'Source : tanzil.net';
            source.appendChild(link);
            card.appendChild(source);
        }
        return card;
    }

    function normalizeDailyContentEntry(entry) {
        if (entry.type || !entry.reference) return entry;
        const match = /^(.*?)\s+(\d+):(\d+)$/.exec(entry.reference);
        if (!match) return entry;
        return {
            ...entry,
            type: 'quran',
            citation: {
                surah: match[1],
                chapter: Number(match[2]),
                verse: Number(match[3])
            }
        };
    }

    async function refreshDailyContent() {
        if (dailyContentBusy) return;
        const cached = readJson(DAILY_CONTENT_CACHE_KEY);
        if (cached && cached.package && Array.isArray(cached.package.entries)) {
            dailyContentPackage = cached.package;
            renderAnnouncements(currentAnnouncements);
            if (Date.now() - cached.savedAt < ANNOUNCEMENTS_TTL_MS) return;
        }

        dailyContentBusy = true;
        try {
            const response = await fetch('/api/public/daily-content/', {
                cache: 'no-cache',
                credentials: 'same-origin'
            });
            if (!response.ok) throw new Error('Daily content could not be loaded.');
            const packageData = await response.json();
            if (!packageData.success || !Array.isArray(packageData.entries)) {
                throw new Error('The daily content response was invalid.');
            }
            dailyContentPackage = packageData;
            saveJson(DAILY_CONTENT_CACHE_KEY, {savedAt: Date.now(), package: packageData});
            renderAnnouncements(currentAnnouncements);
        } catch (error) {
            console.warn('[Takbir] Could not refresh daily content:', error);
        } finally {
            dailyContentBusy = false;
        }
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
