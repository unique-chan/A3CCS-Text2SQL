# View Reference

본 문서는 현재 catalog에 포함된 전체 뷰에 대한 설명문입니다.  
변경 이력이나 기존 뷰 대비 차이점은 적지 않고, 각 뷰의 역할과 해석 기준만 정리합니다.

---

## 1. `v_units_snapshot`

유닛 스냅샷 상세 조회용 뷰입니다.  
아군(`b`)과 적군(`op`) 각각에 대해 초기 시점(`initial`)과 현재 시점(`current`)의 유닛 상태를 하나의 뷰에서 제공합니다.

### 목적
- 기준 시점 유닛 상태 조회
- 초기/현재 비교
- 아군/적군 비교
- 상세 위치, 타입, 손상 상태 확인

### 기준
- `phase='initial'`: 각 진영의 최소 `datetime`
- `phase='current'`: 각 진영의 최대 `datetime`

### 주요 컬럼
- `phase`
- `snapshotid`
- `ref_datetime`
- `side`
- `unitname`
- `groupname`
- `unittype`
- `posx`, `posy`, `posz`
- `damage`
- `objectparent`

### 해석
행 하나는 특정 기준 시점에 선택된 개별 유닛 상태를 의미합니다.

---

## 2. `v_units_snapshot_count`

유닛 스냅샷 집계 뷰입니다.  
`v_units_snapshot`를 기준으로 시점과 진영별 유닛 수를 제공합니다.

### 목적
- 병력 규모 요약
- 초기/현재 수량 비교
- 진영별 수량 비교
- 대시보드용 카운트 제공

### 주요 컬럼
- `phase`
- `side`
- `ref_datetime`
- `unit_count`

### 해석
행 하나는 특정 `phase`와 `side` 조합에 대한 총 유닛 수입니다.

---

## 3. `v_vehicles_snapshot`

장비 스냅샷 상세 조회용 뷰입니다.  
아군(`b`)과 적군(`op`) 각각에 대해 초기 시점과 현재 시점의 장비 상태를 하나의 뷰에서 제공합니다.

### 목적
- 기준 시점 장비 상태 조회
- 초기/현재 장비 비교
- 진영별 장비 배치 확인
- 손상 및 위치 확인

### 기준
- `phase='initial'`: 각 진영의 최소 `datetime`
- `phase='current'`: 각 진영의 최대 `datetime`

### 주요 컬럼
- `phase`
- `snapshotid`
- `ref_datetime`
- `side`
- `vehiclename`
- `groupname`
- `vehicletype`
- `posx`, `posy`, `posz`
- `damage`
- `hitpointjson`

### 해석
행 하나는 특정 기준 시점에 선택된 개별 장비 상태를 의미합니다.

---

## 4. `v_vehicles_snapshot_count`

장비 스냅샷 집계 뷰입니다.  
`v_vehicles_snapshot`를 기준으로 시점과 진영별 장비 수를 제공합니다.

### 목적
- 장비 규모 요약
- 초기/현재 장비 수 비교
- 진영별 장비 수 비교
- 리포트용 카운트 제공

### 주요 컬럼
- `phase`
- `side`
- `ref_datetime`
- `vehicle_count`

### 해석
행 하나는 특정 `phase`와 `side` 조합에 대한 총 장비 수입니다.

---

## 5. `v_current_friendly_enemy_group_distance`

현재 시점 기준 아군 그룹과 적군 그룹 사이의 3차원 거리를 계산한 뷰입니다.

### 목적
- 그룹 단위 근접도 분석
- 접촉 가능성이 높은 그룹 쌍 식별
- 전선 간격 또는 충돌 가능성 점검

### 계산 방식
1. `snapshots`의 최대 `datetime`를 현재 기준 시점으로 설정
2. 아군/적군 각각에 대해 그룹별 중심점(centroid) 계산
3. 각 그룹에서 기준 시점에 가장 가까운 관측값 1개 선택
4. 아군 그룹 중심과 적군 그룹 중심 간 3D Euclidean distance 계산

### 주요 컬럼
- `ref_datetime`
- `friendly_groupname`
- `friendly_datetime`
- `friendly_posx`, `friendly_posy`, `friendly_posz`
- `enemy_groupname`
- `enemy_datetime`
- `enemy_posx`, `enemy_posy`, `enemy_posz`
- `distance_3d`

### 해석
행 하나는 아군 그룹 하나와 적군 그룹 하나의 현재 기준 거리입니다.  
정렬은 거리 오름차순이므로, 가장 가까운 그룹 쌍이 먼저 보입니다.

---

## 6. `v_current_friendly_enemy_unit_distance`

현재 시점 기준 아군 유닛과 적군 유닛 사이의 3차원 거리를 계산한 뷰입니다.

### 목적
- 개별 유닛 근접도 분석
- 직접 교전 가능성이 높은 유닛 쌍 탐색
- 세부 전술 수준 거리 분석

### 계산 방식
1. `snapshots`의 최대 `datetime`를 현재 기준 시점으로 설정
2. 각 유닛별로 기준 시점에 가장 가까운 관측값 1개 선택
3. 아군 유닛과 적군 유닛의 모든 조합에 대해 3D distance 계산

### 주요 컬럼
- `ref_datetime`
- `friendly_unitname`
- `friendly_groupname`
- `friendly_unittype`
- `friendly_datetime`
- `friendly_posx`, `friendly_posy`, `friendly_posz`
- `enemy_unitname`
- `enemy_groupname`
- `enemy_unittype`
- `enemy_datetime`
- `enemy_posx`, `enemy_posy`, `enemy_posz`
- `distance_3d`

### 해석
행 하나는 아군 유닛 하나와 적군 유닛 하나의 현재 기준 거리입니다.

---

## 7. `v_current_friendly_enemy_vehicle_distance`

현재 시점 기준 아군 장비와 적군 장비 사이의 3차원 거리를 계산한 뷰입니다.

### 목적
- 개별 장비 근접도 분석
- 장비 간 교전 또는 접촉 가능성 분석
- 차량/장비 배치 비교

### 계산 방식
1. `snapshots`의 최대 `datetime`를 현재 기준 시점으로 설정
2. 각 장비별로 기준 시점에 가장 가까운 관측값 1개 선택
3. 아군 장비와 적군 장비의 모든 조합에 대해 3D distance 계산

### 주요 컬럼
- `ref_datetime`
- `friendly_vehiclename`
- `friendly_groupname`
- `friendly_vehicletype`
- `friendly_datetime`
- `friendly_posx`, `friendly_posy`, `friendly_posz`
- `enemy_vehiclename`
- `enemy_groupname`
- `enemy_vehicletype`
- `enemy_datetime`
- `enemy_posx`, `enemy_posy`, `enemy_posz`
- `distance_3d`

### 해석
행 하나는 아군 장비 하나와 적군 장비 하나의 현재 기준 거리입니다.

---

## 8. `v_friendly_unit_speed_trend`

아군 유닛의 시간대별 이동 속도 변화를 계산한 뷰입니다.

### 목적
- 기동성 변화 추적
- 급가속/정지 구간 탐지
- 시간 흐름에 따른 이동 패턴 파악

### 계산 방식
1. 같은 `unitname` 내에서 직전 시점 좌표와 시간을 `LAG`로 조회
2. 현재 좌표와 직전 좌표의 거리 차이를 계산
3. 시간 차이(`dt_seconds`)로 나누어 속도 계산

### 주요 컬럼
- `unitname`
- `groupname`
- `unittype`
- `datetime`
- `prev_datetime`
- `dt_seconds`
- `distance_delta`
- `speed`

### 해석
행 하나는 특정 유닛의 한 시점 이동 구간에 대한 속도 계산 결과입니다.  
`speed`는 직전 시점에서 현재 시점까지의 평균 이동 속도입니다.

---

## 9. `v_friendly_vehicle_speed_trend`

아군 장비의 시간대별 이동 속도 변화를 계산한 뷰입니다.

### 목적
- 장비 기동 추적
- 이동/정지 패턴 분석
- 장비별 속도 변화 분석

### 계산 방식
- `vehiclename`별 직전 좌표/시간을 사용해 구간 이동거리와 시간 차이를 계산
- 이동거리 ÷ 시간차로 속도 산출

### 주요 컬럼
- `vehiclename`
- `groupname`
- `vehicletype`
- `datetime`
- `prev_datetime`
- `dt_seconds`
- `distance_delta`
- `speed`

### 해석
행 하나는 특정 장비의 연속 두 시점 사이 속도 값입니다.

---

## 10. `v_enemy_unit_speed_trend`

적군 유닛의 시간대별 이동 속도 변화를 계산한 뷰입니다.

### 목적
- 적군 기동성 파악
- 접근/후퇴 패턴 분석
- 시간대별 이동량 추적

### 계산 방식
아군 유닛 속도 추이 뷰와 동일하되, `side='op'` 유닛만 대상으로 합니다.

### 주요 컬럼
- `unitname`
- `groupname`
- `unittype`
- `datetime`
- `prev_datetime`
- `dt_seconds`
- `distance_delta`
- `speed`

### 해석
행 하나는 특정 적군 유닛의 연속 구간 속도입니다.

---

## 11. `v_enemy_vehicle_speed_trend`

적군 장비의 시간대별 이동 속도 변화를 계산한 뷰입니다.

### 목적
- 적군 장비 기동 추적
- 차량/장비 이동 패턴 분석
- 위협 접근 속도 분석

### 계산 방식
아군 장비 속도 추이 뷰와 동일하되, `side='op'` 장비만 대상으로 합니다.

### 주요 컬럼
- `vehiclename`
- `groupname`
- `vehicletype`
- `datetime`
- `prev_datetime`
- `dt_seconds`
- `distance_delta`
- `speed`

### 해석
행 하나는 특정 적군 장비의 연속 구간 속도입니다.

---

## 12. `v_friendly_unit_ammo_trend`

아군 유닛별 탄약 총량 변화 추이를 계산한 뷰입니다.

### 목적
- 탄약 소모 추세 파악
- 재보급 필요성 탐지
- 유닛별 전투 소모량 비교

### 계산 방식
1. `units_ammo`에서 같은 `unitname`, `datetime`에 대한 탄약 수량 합계 계산
2. 직전 시점 총탄약량을 `LAG`로 조회
3. 현재 총량 - 직전 총량으로 `ammo_change` 계산

### 주요 컬럼
- `unitname`
- `datetime`
- `prev_datetime`
- `total_ammo_count`
- `prev_total_ammo_count`
- `ammo_change`

### 해석
- `ammo_change < 0`: 탄약 소모
- `ammo_change = 0`: 변화 없음
- `ammo_change > 0`: 탄약 증가 또는 재보급

---

## 13. `v_friendly_vehicle_ammo_trend`

아군 장비별 탄약 총량 변화 추이를 계산한 뷰입니다.

### 목적
- 장비 탄약 소모 추세 분석
- 재무장 여부 확인
- 장비별 전투 지속성 판단

### 계산 방식
`vehicles_ammo`를 사용해 장비별 시점 총탄약량과 직전 시점 총탄약량 차이를 계산합니다.

### 주요 컬럼
- `vehiclename`
- `datetime`
- `prev_datetime`
- `total_ammo_count`
- `prev_total_ammo_count`
- `ammo_change`

### 해석
값의 부호 해석은 유닛 탄약 추이와 동일합니다.

---

## 14. `v_enemy_unit_ammo_trend`

적군 유닛별 탄약 총량 변화 추이를 계산한 뷰입니다.

### 목적
- 적군 화력 소모 추정
- 지속 전투 가능성 판단
- 재보급 정황 탐지

### 계산 방식
아군 유닛 탄약 추이 뷰와 동일하되, `side='op'`만 대상으로 합니다.

### 주요 컬럼
- `unitname`
- `datetime`
- `prev_datetime`
- `total_ammo_count`
- `prev_total_ammo_count`
- `ammo_change`

### 해석
`ammo_change`를 통해 적군의 소모 또는 증강 흐름을 볼 수 있습니다.

---

## 15. `v_enemy_vehicle_ammo_trend`

적군 장비별 탄약 총량 변화 추이를 계산한 뷰입니다.

### 목적
- 적군 장비 화력 자원 변화 확인
- 장비별 교전 지속성 분석
- 보급 징후 파악

### 계산 방식
아군 장비 탄약 추이 뷰와 동일하되, `side='op'` 장비만 대상으로 합니다.

### 주요 컬럼
- `vehiclename`
- `datetime`
- `prev_datetime`
- `total_ammo_count`
- `prev_total_ammo_count`
- `ammo_change`

### 해석
음수는 소모, 양수는 증가를 의미합니다.

---

## 16. `event_dammaged_dedup`

피해 이벤트 원본 테이블 `event_dammaged`를 `(datetime, shooter, targetunit)` 기준으로 중복 제거한 canonical 뷰입니다.

### 목적
- 이벤트 중복 제거
- 후속 집계의 기준 이벤트셋 제공
- 동일 시점 동일 공격자-피격자 조합 정리

### 계산 방식
- `datetime`, `shooter`, `targetunit` 기준으로 그룹화
- 원본 행 수를 `raw_row_count`로 유지

### 주요 컬럼
- `event_time`
- `shooter`
- `targetunit`
- `raw_row_count`

### 해석
행 하나는 중복 제거된 고유 피해 이벤트 키 1건입니다.  
`raw_row_count`는 동일 이벤트가 원본에 몇 번 존재했는지를 보여줍니다.

---

## 17. `event_dammaged_by_attacker`

중복 제거된 피해 이벤트를 공격자 기준으로 집계한 뷰입니다.

### 목적
- 공격자별 피해 유발 규모 집계
- 특정 시점 공격 주체 파악
- 공격자별 피격 대상 다양성 확인

### 계산 방식
- `event_dammaged_dedup`를 기준으로
- `event_time`, `shooter`별 그룹화
- 공격자가 맞힌 서로 다른 `targetunit` 수를 `victim_count`로 계산

### 주요 컬럼
- `event_time`
- `attacker`
- `victim_count`

### 해석
행 하나는 특정 시점의 특정 공격자가 몇 개의 서로 다른 피해 대상을 만들었는지를 의미합니다.

---

## 18. `event_dammaged_by_victim`

중복 제거된 피해 이벤트를 피격자 기준으로 집계한 뷰입니다.

### 목적
- 피격자별 공격 집중도 집계
- 동일 시점 다중 공격 여부 파악
- 특정 피해 대상의 위협 수준 확인

### 계산 방식
- `event_dammaged_dedup`를 기준으로
- `event_time`, `targetunit`별 그룹화
- 해당 피격자를 공격한 서로 다른 `shooter` 수를 `attack_count`로 계산

### 주요 컬럼
- `event_time`
- `victim`
- `attack_count`

### 해석
행 하나는 특정 시점의 특정 피격자가 몇 명의 서로 다른 공격자로부터 공격받았는지를 의미합니다.

---

## 공통 해석 주의

### 현재 시점 기준 거리 뷰
거리 뷰 3종은 모두 `snapshots`의 최대 `datetime`를 기준 시점으로 사용합니다.  
개별 그룹/유닛/장비의 실제 기록 시각은 기준 시점과 완전히 같지 않을 수 있으며, 가장 가까운 기록이 선택됩니다.

### 속도 추이 뷰
속도는 연속 두 시점 사이의 평균 이동 속도입니다.  
샘플링 간격이 길거나 불규칙하면 순간 속도가 아니라 구간 평균으로 해석해야 합니다.

### 탄약 추이 뷰
탄약 증감은 총합 기준입니다.  
개별 탄종별 변화가 아니라 해당 객체의 전체 탄약량 순변화를 보여줍니다.

### 피해 이벤트 뷰
이벤트 집계는 먼저 `event_dammaged_dedup`으로 중복을 정리한 뒤 계산됩니다.  
따라서 원본 raw row 수와 최종 집계 수는 다를 수 있습니다.
