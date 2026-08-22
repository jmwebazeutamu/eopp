import { Alert, App, Checkbox, DatePicker, Form, Input, InputNumber, Modal, Radio, Select } from "antd";
import { useEffect, useState } from "react";

import { api, errorMessage, formErrors } from "../../api/client";
import type { Location, Paginated, WltMobilisationEvent } from "../../api/types";
import { useAuth } from "../../auth/AuthContext";
import { useLang } from "../../i18n/LanguageContext";

/**
 * Drafting a group — handbook 3.4, steps 1 and 2 on one form.
 *
 * The shape of this form is the rule it enforces: **a group starts with a
 * community meeting endorsing it**, so the meeting is the first field and the
 * name is the second. `formation.open_draft` refuses to draft from a refused
 * endorsement, and until this screen existed that refusal was only reachable
 * from a shell — the API saved the serializer directly and skipped it.
 *
 * Three decisions worth keeping:
 *
 * - **No kebele field.** The group's kebele is the meeting's kebele, derived
 *   server-side. Offering it invites a hand-typed one that disagrees, and then
 *   the group scopes to one place and reports in another. Same reasoning as
 *   `RegisterWomanModal`, and as `Case.woreda`.
 * - **Only endorsed meetings are offered** (`?endorsed_only=true`). A picker
 *   that listed a refused meeting would collect a submission the server is
 *   bound to reject, and the facilitator would read the refusal as a fault.
 * - **Recording a refusal is on this form too.** A community that declines is
 *   programme learning, not a dead end (assertion A30) — and a facilitator who
 *   had no way to record it here would have no way to record it at all. When
 *   she chooses "did not endorse", the form stops asking for a group name and
 *   says what it is going to do instead.
 */
export default function DraftGroupModal({
  open,
  onClose,
  onDone,
  initialKebele,
}: {
  open: boolean;
  onClose: () => void;
  onDone: () => void;
  initialKebele?: string;
}) {
  const { message } = App.useApp();
  const { t } = useLang();
  const [form] = Form.useForm();
  const { user } = useAuth();

  const [events, setEvents] = useState<WltMobilisationEvent[]>([]);
  const [kebeles, setKebeles] = useState<Location[]>([]);
  const [submitting, setSubmitting] = useState(false);
  const [facilitators, setFacilitators] = useState<Array<{ id: string; full_name: string }>>([]);
  /** The lookup errored, as opposed to genuinely returning nobody. */
  const [pickerFailed, setPickerFailed] = useState(false);
  const [popupOpen, setPopupOpen] = useState(false);
  /** Draft from a meeting already recorded, or record the meeting now. */
  const [source, setSource] = useState<"existing" | "new">("existing");
  const [endorsed, setEndorsed] = useState(true);

  useEffect(() => {
    if (!open) return;
    let cancelled = false;
    void (async () => {
      try {
        const [meetings, locations] = await Promise.all([
          api.get<Paginated<WltMobilisationEvent>>("/wlt/mobilisation-events/", {
            params: { endorsed_only: true, page_size: 200 },
          }),
          api.get<Location[]>("/locations/"),
        ]);
        if (cancelled) return;
        setEvents(meetings.data.results);
        setKebeles(locations.data.filter((row) => row.level === "KEBELE"));
        // A facilitator convening her first meeting has none to choose from,
        // so the form opens on the branch she can actually complete.
        setSource(initialKebele ? "new" : meetings.data.results.length ? "existing" : "new");
        if (initialKebele) form.setFieldValue("kebele", initialKebele);
      } catch {
        if (cancelled) return;
        setEvents([]);
        setKebeles([]);
        setSource("new");
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [form, initialKebele, open]);

  const selectedMeeting = Form.useWatch("mobilisation_event", form);
  const selectedKebele = Form.useWatch("kebele", form);
  const facilitatorKebele = source === "new"
    ? selectedKebele
    : events.find((event) => event.id === selectedMeeting)?.kebele;
  const recordingRefusal = source === "new" && !endorsed;

  useEffect(() => {
    if (!open || !facilitatorKebele || recordingRefusal) {
      setFacilitators([]);
      return;
    }
    let cancelled = false;
    setPickerFailed(false);
    void api.get<Array<{ id: string; full_name: string }>>("/users/wlt-facilitators/", {
      params: { kebele: facilitatorKebele },
    }).then((response) => {
      if (cancelled) return;
      setFacilitators(response.data);
      const currentIsFacilitator = user?.role === "WLT_FACILITATOR";
      if (!form.getFieldValue("facilitator") && currentIsFacilitator && response.data.some((row) => row.id === user.id)) {
        form.setFieldValue("facilitator", user.id);
      }
    }).catch((error) => {
      // A failed lookup is not an empty one. This swallowed a 500 and rendered
      // "no facilitator covers this kebele", so a crash read as a legitimate
      // answer and the blocker survived three rounds of testing.
      if (cancelled) return;
      setFacilitators([]);
      setPickerFailed(true);
      message.error(errorMessage(error, t("wlt.facilitatorsLoadFailed")));
    });
    return () => { cancelled = true; };
  }, [facilitatorKebele, form, message, open, recordingRefusal, t, user]);

  function close(force = false) {
    if (!force && form.isFieldsTouched()) {
      Modal.confirm({ title: "Discard this draft group?", content: "Your unsaved entries will be lost.", okText: "Discard", okButtonProps: { danger: true }, onOk: () => close(true) });
      return;
    }
    form.resetFields();
    setSource("existing");
    setEndorsed(true);
    onClose();
  }

  const submit = async (values: Record<string, unknown>) => {
    setSubmitting(true);
    try {
      let eventId = values.mobilisation_event as string | undefined;

      if (source === "new") {
        const held = values.held_on as { format?: (pattern: string) => string } | undefined;
        const meeting = await api.post<WltMobilisationEvent>("/wlt/mobilisation-events/", {
          kebele: values.kebele,
          held_on: held?.format ? held.format("YYYY-MM-DD") : undefined,
          endorsement_obtained: endorsed,
          endorsement_note: values.endorsement_note || "",
          attendees_potential: values.attendees_potential ?? null,
          attendees_husbands: values.attendees_husbands ?? null,
          attendees_elders: values.attendees_elders ?? null,
          attendees_leaders: values.attendees_leaders ?? null,
        });

        // A refused endorsement closes the mobilisation. The row is the whole
        // point — it is what explains a kebele with no groups in it — so this
        // is a success, and the message says so rather than apologising.
        if (!endorsed) {
          message.success(t("wlt.meetingRecordedNoGroup"));
          close(true);
          onDone();
          return;
        }
        eventId = meeting.data.id;
      }

      const created = await api.post<{ name: string }>("/wlt/groups/", {
        name: values.name,
        mobilisation_event: eventId,
        facilitator: values.facilitator,
      });
      message.success(t("wlt.groupDrafted", { name: created.data.name }));
      close(true);
      onDone();
    } catch (error) {
      const fields = formErrors(error);
      if (fields.length) form.setFields(fields);
      message.error(errorMessage(error, t("wlt.groupDraftFailed")));
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Modal
      open={open}
      onCancel={() => close()}
      onOk={() => form.submit()}
      okText={recordingRefusal ? t("wlt.recordRefusal") : t("wlt.draftGroup")}
      confirmLoading={submitting}
      title={t("wlt.draftGroupTitle")}
      destroyOnHidden
      keyboard={!popupOpen}
    >
      <Form form={form} layout="vertical" onFinish={submit} requiredMark="optional">
        <Alert
          type="info"
          showIcon
          style={{ marginBottom: 16 }}
          message={t("wlt.draftGroupIntro")}
          description={t("wlt.draftGroupIntroBody")}
        />

        <Form.Item label={t("wlt.communityMeeting")}>
          <Radio.Group
            value={source}
            onChange={(event) => setSource(event.target.value)}
            options={[
              { value: "existing", label: t("wlt.useRecordedMeeting"), disabled: events.length === 0 },
              { value: "new", label: t("wlt.recordMeetingNow") },
            ]}
          />
        </Form.Item>

        {source === "existing" && (
          <Form.Item
            name="mobilisation_event"
            label={t("wlt.endorsedMeeting")}
            rules={[{ required: true, message: t("wlt.endorsedMeetingRequired") }]}
            extra={t("wlt.endorsedMeetingHelp")}
          >
            <Select
              onOpenChange={setPopupOpen}
              showSearch
              optionFilterProp="label"
              placeholder={t("wlt.chooseMeeting")}
              options={events.map((event) => ({
                value: event.id,
                label: `${event.kebele_name} · ${event.held_on}${
                  event.groups_drafted ? ` · ${t("wlt.groupsAlreadyDrafted", { count: event.groups_drafted })}` : ""
                }`,
              }))}
            />
          </Form.Item>
        )}

        {source === "new" && (
          <>
            <Form.Item
              name="kebele"
              label={t("wlt.kebele")}
              rules={[{ required: true, message: t("wlt.kebeleRequired") }]}
              extra={t("wlt.kebeleDerivesGroup")}
            >
              <Select
                onOpenChange={setPopupOpen}
                showSearch
                optionFilterProp="label"
                placeholder={t("wlt.chooseKebele")}
                options={kebeles.map((kebele) => ({ value: kebele.code, label: kebele.name }))}
              />
            </Form.Item>

            <Form.Item
              name="held_on"
              label={t("wlt.meetingHeldOn")}
              rules={[{ required: true, message: t("wlt.meetingHeldOnRequired") }]}
            >
              <DatePicker onOpenChange={setPopupOpen} style={{ width: "100%" }} placement="bottomLeft" needConfirm={false} onKeyDown={(event) => { if (event.key === "Enter") event.currentTarget.blur(); }} />
            </Form.Item>

            {/* Counts by category, as the handbook asks. No attendee names: it
                is a community meeting, not a roster. */}
            <div style={{ display: "grid", gridTemplateColumns: "repeat(2, minmax(0, 1fr))", gap: 12 }}>
              <Form.Item name="attendees_potential" label={t("wlt.attendeesPotential")}>
                <InputNumber min={0} style={{ width: "100%" }} />
              </Form.Item>
              <Form.Item name="attendees_husbands" label={t("wlt.attendeesHusbands")}>
                <InputNumber min={0} style={{ width: "100%" }} />
              </Form.Item>
              <Form.Item name="attendees_elders" label={t("wlt.attendeesElders")}>
                <InputNumber min={0} style={{ width: "100%" }} />
              </Form.Item>
              <Form.Item name="attendees_leaders" label={t("wlt.attendeesLeaders")}>
                <InputNumber min={0} style={{ width: "100%" }} />
              </Form.Item>
            </div>

            <Form.Item>
              <Checkbox checked={endorsed} onChange={(event) => setEndorsed(event.target.checked)}>
                {t("wlt.endorsementObtained")}
              </Checkbox>
            </Form.Item>

            <Form.Item
              name="endorsement_note"
              label={endorsed ? t("wlt.endorsementNote") : t("wlt.refusalReason")}
              rules={
                endorsed ? [] : [{ required: true, message: t("wlt.refusalReasonRequired") }]
              }
              extra={endorsed ? undefined : t("wlt.refusalReasonHelp")}
            >
              <Input.TextArea rows={3} />
            </Form.Item>

            {recordingRefusal && (
              <Alert
                type="warning"
                showIcon
                style={{ marginBottom: 16 }}
                message={t("wlt.refusalClosesMobilisation")}
                description={t("wlt.refusalClosesMobilisationBody")}
              />
            )}
          </>
        )}

        {!recordingRefusal && (
          <>
          <Form.Item
            name="facilitator"
            label="Facilitator"
            rules={[{ required: true, message: "Choose the facilitator who will run this group." }]}
            extra={facilitatorKebele ? "Only facilitators whose WLT scope covers this kebele are shown." : "Choose the meeting or kebele first."}
          >
            <Select
              onOpenChange={setPopupOpen}
              showSearch
              optionFilterProp="label"
              disabled={!facilitatorKebele}
              placeholder="Choose a facilitator"
              options={facilitators.map((facilitator) => ({ value: facilitator.id, label: facilitator.full_name }))}
              notFoundContent={
                pickerFailed
                  ? t("wlt.facilitatorsLoadFailed")
                  : facilitatorKebele
                    ? t("wlt.noFacilitatorCovers")
                    : t("wlt.chooseKebeleFirst")
              }
            />
          </Form.Item>
          <Form.Item
            name="name"
            label={t("wlt.groupName")}
            rules={[{ required: true, message: t("wlt.groupNameRequired") }]}
            extra={t("wlt.groupNameHelp")}
          >
            <Input />
          </Form.Item>
          </>
        )}
      </Form>
    </Modal>
  );
}
