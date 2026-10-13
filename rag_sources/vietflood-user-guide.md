---
title: VietFlood user guide for new users
description: A role-based tutor guide to the VietFlood web and mobile interfaces.
source_ids: [G01]
source_url: https://github.com/dnchuong17/Vietflood_FE_Clone
language: en
representation: user-guide
accessed_at: 2026-10-12
rechecked_at: 2026-10-12
verification_status: VERIFIED_AGAINST_REPOSITORY
medical_review_required: false
chemical_dosing_review_required: false
tags:
  - VietFlood
  - user-guide
  - tutorial
---

# VietFlood user guide for new users

This guide is for a tutor, support person, or assistant helping someone learn VietFlood. It describes the web interface and the companion mobile app, explains the three account roles, and gives a consistent way to answer questions about controls that appear on screen.

## 1. What VietFlood does

VietFlood helps people view weather context, report flood incidents or needs, follow report progress, and coordinate relief. The web app and mobile app do not show identical features. On web, signed-in users can also use the VietFlood assistant chat. Role and account permissions control operational pages.

The web app is in Vietnamese. The routes below are included so a tutor can direct a user even if their screen is currently in another language or layout. On smaller web screens, the role tabs move to the fixed bottom navigation. On desktop, they appear in the top navigation.

## 2. Start here: access and account

### Welcome, sign-in, and registration

Before sign-in, the web offers **Đăng nhập** (sign in) and **Đăng ký** (register). Ask the user to enter the credentials used for their VietFlood account. Registration creates a citizen account; relief and admin access should be provided by an authorized administrator rather than selected as a public registration option. After successful sign-in, the app shows pages allowed for the account role.

If the user cannot sign in, check that they are using the right account and that the network is available. If access to an operational page is denied, ask an administrator to check their assigned role. Never ask the user to share their password in chat or support messages.

### Shared web header

- **VietFlood mark/name** returns to the app’s home entry point.
- **Role tabs** are the main navigation and differ by role (see below).
- **Theme control** switches the color theme.
- **Account name** identifies the signed-in account.
- **Đăng xuất** ends the local signed-in session and returns to the public home screen.

The active tab is highlighted. A tab may be absent because the current role does not have access, rather than because the page has failed to load.

## 3. Roles and what each person can do

| Role shown in the app | Intended user | Main capabilities |
| --- | --- | --- |
| **Người dân** (citizen) | A resident or person requesting help | View weather map, create and manage their own reports, view tracking, chat with the assistant, and manage their profile. |
| **Đội cứu trợ** (relief) | A responder or relief coordinator | Review operational reports, update their status, coordinate assignments, view tracking, and review user information. |
| **Quản trị viên** (admin) | A system administrator | Has relief operations access and can manage user roles and accounts, including deleting accounts where permitted. |

Role controls what the interface displays. Citizen report access is limited to their own submissions; operational roles can review the broader report queue. Relief users can manage users in the current web UI, but only admins can delete users. Admins should assign only the role needed for a person’s work.

### Citizen web navigation

**Bản đồ** (`/trang-chu`), **Trợ lý** (`/chat`), **Báo cáo** (`/bao-cao`), **Theo dõi** (`/theo-doi`), and **Hồ sơ** (`/ho-so`).

### Relief and admin web navigation

**Cứu trợ** (`/cuu-tro`), **Trợ lý** (`/chat`), **Báo cáo** (`/bao-cao`), **Theo dõi** (`/theo-doi`), **Người dùng** (`/nguoi-dung`), and **Hồ sơ** (`/ho-so`). The Cứu trợ area also provides the assignment workflow; `/phan-cong` is the assignment view. Operational users can access **Tổng quan** (`/tong-quan`) as a direct page where available.

## 4. Web screens and their visible controls

### Bản đồ Windy — citizen home (`/trang-chu`)

The map is the main visual area. It provides weather context for the selected location. The map tools let the user choose a weather layer such as rain, wind, temperature, humidity, clouds, or pressure and open a weather statistics panel. Explain that these are map overlays for situational awareness; they are not a verified VietFlood incident report. Encourage the user to check the location and time context before relying on a weather layer.

### Trợ lý VietFlood (`/chat`)

The chat workspace includes a conversation area, a question input (**Nhập câu hỏi của bạn...**), a send button, and conversation history. On mobile width, history opens from its history button; on desktop it is shown in a side panel. A user can start a new question by typing and sending it, select a previous conversation, copy an answer, or delete a conversation after confirming the prompt.

The assistant can answer flood-safety questions, explain the report form, and—when signed in—read the current user’s report status. For recent flood-location questions it may show area-level summaries of verified VietFlood reports from the last 24 hours. It does not reveal reporter identity, exact address, coordinates, or report descriptions in those summaries. If an answer concerns immediate danger, direct the user to local emergency services and nearby responders; chat is not an emergency dispatch channel. For action prompts, read any confirmation text before approving an operation.

If the chat shows a loading state, wait for the response. If it shows an error, retry once when connectivity is available. The user can still use the report and map pages independently.

### Báo cáo (`/bao-cao`)

The page has two important tasks: create a report and find or review reports. The report form collects incident/report category, description, location (province/city, ward/commune, street or house address, and GPS coordinates when available), and optional supporting information such as a photo. Use the most accurate location the user can provide. If location permission is declined or GPS is unavailable, enter the address; the page may ask the user to confirm sending without coordinates.

The report list includes search (report code, location, report type, or description) and a status filter. Selecting a report opens its detail view. Report detail can show the report’s category, description, location, reporter/contact details, evidence, and current status, depending on the viewer’s permissions and available data. The reporter can edit their own report where allowed; operational users review the queue and update status.

Statuses are **Chờ xử lý** (pending), **Đã xác minh** (verified), **Đã xử lý** (resolved), and **Từ chối** (rejected). A status is the current recorded workflow state, not a guarantee of rescue arrival time. If a list appears empty, check the search text and status filter first, then refresh/reopen the page.

### Cứu trợ / Phân công (`/cuu-tro`, `/phan-cong`)

This is an operational queue for relief and admin roles. It presents report counts and report cards, with priority/status cues, a search field for address, category, or reporter, and queue filters. A card can lead to a report detail containing location and contact information for operational follow-up. Responders use status actions to record verification, resolution, or rejection, and the assignment view to organize follow-up. Read report details carefully before contacting a reporter; only use contact details for relief coordination.

Priority is a triage aid derived from the report information. It is not an official guarantee of severity or a dispatch assignment by itself. If no reports appear, clear search/filter selections and refresh the queue.

### Tổng quan (`/tong-quan`)

For operational roles, the overview dashboard summarizes the system and provides tabbed summaries. Numbers depend on current report/user data. Use it to understand workload and then open the relevant queue or report for action; summary counts do not replace the report record.

### Theo dõi trực tiếp (`/theo-doi`)

The tracking screen shows live locations shared by users who have enabled sharing. Operational users can inspect current shared locations and open directions where available. A citizen uses tracking to share their own location when requesting or coordinating active help; sharing is distinct from submitting a report. Explain how to stop sharing if the user no longer wants their location visible. If the map is empty, nobody may currently be sharing, or location/network permission may be unavailable. Location can become stale if a device goes offline.

### Người dùng (`/nguoi-dung`) — relief and admin

The user-management page provides a searchable list and account summaries. Selecting a user exposes profile/report context and permitted profile updates. Relief and admins can review/manage users; role changes and deletion are subject to permissions. Admin-only delete actions may ask for confirmation. Explain that role changes affect navigation and available data after the account refreshes or signs in again. Do not delete or change a user’s role without an authorized operational reason.

### Hồ sơ và cài đặt (`/ho-so`)

The page shows a personal overview (for example, account identity, contact details, and account dates), editable profile fields, quick actions, password fields, and help content. Users can update name/contact and location fields such as province/city, ward/commune, and address. The password area asks for current password, new password, and confirmation. If the save action reports that a capability is unavailable, explain that the server currently does not support that operation; do not suggest repeated attempts. Use **Đăng xuất** on shared devices.

### Hướng dẫn (`/huong-dan`)

The in-app guide gives general information about maps, reports, report detail, role-based navigation, profile settings, and response recommendations. It is available to all three web roles, and may also be linked from profile help.

## 5. Mobile app notes

The mobile app uses a bottom tab bar and a role-specific set of screens. Labels can vary with language settings and rollout configuration. Citizen-facing screens include weather/Windy, reports, live tracking, profile, and settings. Relief-facing screens include relief reports/detail, reports, live tracking, volunteer coordination, users overview, and settings. Sign-in and registration begin from Welcome.

Mobile capabilities are controlled by feature rollout flags, so a screen described here may not be present in every build. The mobile code also recognizes older account labels such as `user`/`resident`, `coordinator`, and volunteer-style roles. For user guidance, describe the role and tabs actually shown in that installed build; the canonical web roles documented above are **citizen**, **relief**, and **admin**. If a user sees different tabs, record their platform, app version, and displayed role before escalating.

## 6. How to answer “What is this on my screen?”

Use this sequence so the answer is useful and safe:

1. Ask which page they are on, what role is displayed, and whether they use web or mobile if that is not clear from their message.
2. Name the visible control in the user’s language (for example, **Trạng thái**, **Tìm kiếm**, or **Chia sẻ vị trí**).
3. State what it does and what will happen after pressing it. If an action updates a report, changes access, shares location, or deletes data, say that explicitly before guiding them.
4. Give the next step in order, one screen/action at a time. Do not assume a button exists if the user’s role or build does not show it.
5. For missing or stale data, check role, filters/search, connectivity, and permissions before treating it as a system fault.
6. For urgent safety situations, prioritize immediate local emergency help over app navigation.

Avoid claiming that a report is verified, that a responder has been dispatched, or that a location is current unless the screen explicitly says so. Distinguish weather-map data, user-submitted reports, and live location sharing.

## 7. Quick tutor examples

- **“How do I report flooding?”** Open **Báo cáo**, choose the appropriate report type, describe what is happening, provide the best available location, attach a photo if useful, review the details, then submit. Explain any no-GPS confirmation if it appears.
- **“Where is my report?”** Open **Báo cáo**, clear search/status filters, find the report, open it, and read its current status. A citizen sees their own reports; relief/admin can see the operational queue.
- **“How do I ask for live help?”** Submit a report with a precise location, then use **Theo dõi** to share live location if the installed app offers it and the user wants responders to follow movement. Explain how to stop sharing.
- **“Why can’t I see Người dùng or Cứu trợ?”** Those are operational pages. Ask an admin to confirm that the account has relief or admin access.
- **“What should I do with this map layer?”** Explain what weather variable it displays and how to switch it. Do not present it as an incident report or a promise about conditions at an exact address.

## 8. Tutor reference: terminology

| UI term | Meaning |
| --- | --- |
| **Báo cáo** | A user-submitted record of an incident or need. |
| **Trạng thái** | The recorded progress state of a report. |
| **Đã xác minh** | An operational user has marked the report verified. |
| **Đã xử lý** | The report is marked resolved in the system. |
| **Theo dõi trực tiếp** | Location sharing that can update while a user’s device is online and sharing. |
| **Phân công** | Operational organization/follow-up of relief work. |
| **Người dùng** | Account administration and review, available to operational roles. |

## 9. Scope and maintenance

This is a guide to the UI evidenced in the VietFlood web frontend and companion mobile app source. Web page access and current navigation are described separately from mobile rollout behavior because they are not identical. When a screen changes, update this guide using the page component and role access rules as the source of truth. Avoid documenting backend endpoints or internal implementation details to end users.
