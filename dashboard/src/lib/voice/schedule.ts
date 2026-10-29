import type { LeadStatus, MeetingKind, MeetingStatus, ScheduleKind, ScheduleStatus, Weekday } from "./types";

type Tone = "good" | "neutral" | "warn" | "bad" | "plum";

export const LEADS: Record<LeadStatus, { label: string; tone: Tone; about: string }> = {
    hot: { label: "Hot", tone: "bad", about: "Ready to buy, book or visit soon" },
    warm: { label: "Warm", tone: "warn", about: "Interested, still deciding" },
    cold: { label: "Cold", tone: "neutral", about: "Only asking, little interest" },
    new: { label: "New", tone: "plum", about: "Too little said to tell" },
    not_interested: { label: "Not interested", tone: "neutral", about: "Said no: no follow-ups" },
    customer: { label: "Customer", tone: "good", about: "Bought or joined: no follow-ups" },
};
export const LEAD_ORDER: LeadStatus[] = ["hot", "warm", "cold", "new", "not_interested", "customer"];

export const KINDS: Record<ScheduleKind, { label: string; short: string }> = {
    callback: { label: "Call-back", short: "Call-back" },
    follow_up: { label: "Follow-up", short: "Follow-up" },
    meeting: { label: "Meeting call", short: "Meeting" },
    no_show: { label: "Missed meeting", short: "Missed meeting" },
    person: { label: "For the team", short: "For the team" },
};

export const ITEM_STATUS: Record<ScheduleStatus, { label: string; tone: Tone }> = {
    queued: { label: "Waiting", tone: "neutral" },
    review: { label: "Needs your OK", tone: "warn" },
    calling: { label: "Calling", tone: "plum" },
    todo: { label: "To do", tone: "warn" },
    done: { label: "Done", tone: "good" },
    failed: { label: "Not reached", tone: "bad" },
    cancelled: { label: "Called off", tone: "neutral" },
};

export const MEETING_KINDS: Record<MeetingKind, string> = { online: "Online", in_person: "In person", phone: "Phone" };

export const MEETING_STATUS: Record<MeetingStatus, { label: string; tone: Tone }> = {
    requested: { label: "Waiting for you", tone: "warn" },
    proposed: { label: "Other time offered", tone: "plum" },
    confirmed: { label: "Confirmed", tone: "good" },
    cancelled: { label: "Cancelled", tone: "neutral" },
    expired: { label: "Not answered in time", tone: "neutral" },
    done: { label: "Attended", tone: "good" },
    no_show: { label: "Missed", tone: "bad" },
};

export const WEEKDAYS: { value: Weekday; label: string }[] = [
    { value: "mon", label: "Mon" }, { value: "tue", label: "Tue" }, { value: "wed", label: "Wed" }, { value: "thu", label: "Thu" },
    { value: "fri", label: "Fri" }, { value: "sat", label: "Sat" }, { value: "sun", label: "Sun" },
];

export const TIME_ZONES = [
    { value: "Asia/Kolkata", label: "India (IST)" },
    { value: "Asia/Dubai", label: "Dubai (GST)" },
    { value: "Asia/Singapore", label: "Singapore" },
    { value: "Europe/London", label: "London" },
    { value: "America/New_York", label: "New York" },
    { value: "America/Los_Angeles", label: "Los Angeles" },
    { value: "Australia/Sydney", label: "Sydney" },
];

/** Something in Schedule changed (approved, done, called off): the Voice menu's count is checked again. */
export const SCHEDULE_CHANGED = "nimmi:schedule-changed";
export const scheduleChanged = () => window.dispatchEvent(new Event(SCHEDULE_CHANGED));

/** Today's date (YYYY-MM-DD) in a time zone. */
export function todayIn(timeZone: string, offsetDays = 0) {
    const d = new Date(Date.now() + offsetDays * 86_400_000);
    return new Intl.DateTimeFormat("en-CA", { timeZone, year: "numeric", month: "2-digit", day: "2-digit" }).format(d);
}

function clock(hhmm: string) {
    const [h, m] = hhmm.split(":").map(Number);
    return `${h % 12 || 12}${m ? `:${String(m).padStart(2, "0")}` : ""} ${h < 12 ? "am" : "pm"}`;
}

export const formatClock = clock;

/** "Today, 4:40 pm", "Tomorrow, 11 am", "Fri 31 Oct, 4 pm": a time as the assistant's business sees it. */
export function formatSlot(local: string | null, timeZone: string) {
    if (!local) return "";
    const [day, time] = local.split("T");
    const label = day === todayIn(timeZone) ? "Today" : day === todayIn(timeZone, 1) ? "Tomorrow"
        : new Date(`${day}T12:00:00Z`).toLocaleDateString("en-IN", { weekday: "short", day: "numeric", month: "short", timeZone: "UTC" });
    return `${label}, ${clock(time)}`;
}

/** A day heading for a list grouped by day. */
export function formatDay(day: string, timeZone: string) {
    if (day === todayIn(timeZone)) return "Today";
    if (day === todayIn(timeZone, 1)) return "Tomorrow";
    return new Date(`${day}T12:00:00Z`).toLocaleDateString("en-IN", { weekday: "long", day: "numeric", month: "long", timeZone: "UTC" });
}

export function hoursText(hours: [string, string]) {
    return `${clock(hours[0])} to ${clock(hours[1])}`;
}

/** The WhatsApp template for meeting messages: four values (name, business, when, what's happening). */
export const TEMPLATE_BODY = "Hi {{1}}, about your meeting with {{2}}: {{3}}. {{4}}";
