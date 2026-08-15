import { Col, Form, Input, Row, Select } from "antd";
import { useEffect, useMemo, useState } from "react";
import type { FormInstance } from "antd";

import { api } from "../api/client";
import type { Location } from "../api/types";

/**
 * Cascading Region -> Zone -> Woreda -> Kebele selects.
 *
 * Spec §4.1 stores these as four text fields, but the API validates the whole
 * chain: a woreda that exists under a different zone is rejected. Free-text
 * inputs would let a case manager submit a valid-looking combination and get a
 * field error back, so the picker only ever offers children of what is already
 * chosen.
 *
 * The whole hierarchy is one unpaginated request (~39 rows at pilot scale), so
 * cascading is done in memory rather than with a round trip per level.
 */
export default function LocationPicker({ form }: { form: FormInstance }) {
  const [locations, setLocations] = useState<Location[]>([]);

  const region = Form.useWatch("region", form) as string | undefined;
  const zone = Form.useWatch("zone", form) as string | undefined;
  const woreda = Form.useWatch("woreda", form) as string | undefined;

  useEffect(() => {
    api
      .get<Location[]>("/locations/")
      .then((response) => setLocations(response.data))
      .catch(() => setLocations([]));
  }, []);

  const byLevel = useMemo(
    () => ({
      regions: locations.filter((l) => l.level === "REGION"),
      zones: locations.filter((l) => l.level === "ZONE"),
      woredas: locations.filter((l) => l.level === "WOREDA"),
      kebeles: locations.filter((l) => l.level === "KEBELE"),
    }),
    [locations],
  );

  /** Resolve the selected parent by name, since the form stores names not codes. */
  const selectedRegion = byLevel.regions.find((r) => r.name === region);
  const selectedZone = byLevel.zones.find((z) => z.name === zone && z.parent === selectedRegion?.code);
  const selectedWoreda = byLevel.woredas.find((w) => w.name === woreda && w.parent === selectedZone?.code);

  const zoneOptions = byLevel.zones.filter((z) => z.parent === selectedRegion?.code);
  const woredaOptions = byLevel.woredas.filter((w) => w.parent === selectedZone?.code);
  const kebeleOptions = byLevel.kebeles.filter((k) => k.parent === selectedWoreda?.code);

  const opts = (rows: Location[]) => rows.map((r) => ({ value: r.name, label: r.name }));

  // Changing a level invalidates everything below it; leaving stale children
  // would submit a combination the API rejects.
  const clearBelow = (fields: string[]) => form.setFieldsValue(Object.fromEntries(fields.map((f) => [f, undefined])));

  return (
    <Row gutter={12}>
      <Col xs={24} sm={12}>
        <Form.Item name="region" label="Region" rules={[{ required: true }]}>
          <Select
            options={opts(byLevel.regions)}
            showSearch
            onChange={() => clearBelow(["zone", "woreda", "kebele"])}
            placeholder="Select a region"
          />
        </Form.Item>
      </Col>
      <Col xs={24} sm={12}>
        <Form.Item name="zone" label="Zone" rules={[{ required: true }]}>
          <Select
            options={opts(zoneOptions)}
            showSearch
            disabled={!selectedRegion}
            onChange={() => clearBelow(["woreda", "kebele"])}
            placeholder={selectedRegion ? "Select a zone" : "Choose a region first"}
          />
        </Form.Item>
      </Col>
      <Col xs={24} sm={12}>
        <Form.Item name="woreda" label="Woreda" rules={[{ required: true }]}>
          <Select
            options={opts(woredaOptions)}
            showSearch
            disabled={!selectedZone}
            onChange={() => clearBelow(["kebele"])}
            placeholder={selectedZone ? "Select a woreda" : "Choose a zone first"}
          />
        </Form.Item>
      </Col>
      <Col xs={24} sm={12}>
        <Form.Item
          name="kebele"
          label="Kebele"
          rules={[{ required: true }]}
          // Reference data only lists kebeles for the demo woredas. Where there
          // are none, fall back to a text input rather than blocking
          // registration — and a plain Input, not a tag-mode Select, because
          // that would submit an array where §4.1 stores a string.
          extra={
            selectedWoreda && kebeleOptions.length === 0
              ? "No kebeles listed for this woreda — type the name."
              : undefined
          }
        >
          {selectedWoreda && kebeleOptions.length === 0 ? (
            <Input placeholder="Kebele name" />
          ) : (
            <Select
              options={opts(kebeleOptions)}
              showSearch
              disabled={!selectedWoreda}
              placeholder={selectedWoreda ? "Select a kebele" : "Choose a woreda first"}
            />
          )}
        </Form.Item>
      </Col>
    </Row>
  );
}
