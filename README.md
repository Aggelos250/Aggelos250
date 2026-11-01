# Greek Dynamic Energy Prices — Home Assistant

Custom integration για Home Assistant με τις **τιμές ρεύματος της Αγοράς Επόμενης Ημέρας (ΑΕΗ) για την Ελλάδα** και υπολογισμό της **τελικής τιμής ανά kWh** για όσους έχουν **δυναμικό («πορτοκαλί») τιμολόγιο**, που ισχύει για τα νοικοκυριά από 1/4/2026.

Πηγή δεδομένων: [ENTSO-E Transparency Platform](https://transparency.entsoe.eu/), ζώνη `10YGR-HTSO-----Y`. Υποστηρίζονται διαστήματα 15 λεπτών (PT15M) και ωριαία.

## Τι δίνει

| Οντότητα | Περιγραφή |
|---|---|
| `sensor.…_current_price` | Τρέχουσα τελική τιμή (€/kWh). Τα attributes `today` / `tomorrow` έχουν όλες τις τιμές της μέρας, για γραφήματα (π.χ. ApexCharts) |
| `sensor.…_current_wholesale_price` | Χονδρική τιμή (€/kWh), απενεργοποιημένη από προεπιλογή |
| `sensor.…_next_interval_price` | Τιμή επόμενου διαστήματος |
| `sensor.…_today_average/lowest/highest_price` | Στατιστικά ημέρας |
| `sensor.…_tomorrow_average_price` | Μέση τιμή αύριο (διαθέσιμη μετά τις ~13:00–14:00) |
| `sensor.…_today_cheapest_time` / `…_most_expensive_time` | Πότε είναι η φθηνότερη/ακριβότερη ώρα |
| `sensor.…_cheapest_window_start` | Έναρξη του φθηνότερου **συνεχόμενου** παραθύρου N ωρών από τώρα (π.χ. για πλυντήριο ή φόρτιση αυτοκινήτου) |
| `binary_sensor.…_cheap_hour_now` | `on` όταν τώρα είναι μία από τις N φθηνότερες ώρες της μέρας (π.χ. για θερμοσίφωνα) |

Ο αισθητήρας τρέχουσας τιμής μπαίνει απευθείας στο **Energy Dashboard** («Use an entity with current price»).

### Τύπος τελικής τιμής

```
τελική = (χονδρική + χρέωση προμηθευτή + λοιπές χρεώσεις) × (1 + ΦΠΑ)
```

Τη **χρέωση προμηθευτή** και τις **λοιπές ρυθμιζόμενες χρεώσεις** ανά kWh (δίκτυο, ΥΚΩ, ΕΤΜΕΑΡ, ΕΦΚ) τις βρίσκετε στο συμβόλαιο και στον λογαριασμό σας. Αλλάζουν οποτεδήποτε από *Ρυθμίσεις → Συσκευές & Υπηρεσίες → Greek Dynamic Energy Prices → Ρύθμιση*.

## Εγκατάσταση

1. Πάρτε δωρεάν API token από το ENTSO-E: κάντε λογαριασμό στο transparency.entsoe.eu και στείλτε email στο `transparency@entsoe.eu` με θέμα «Restful API access». Μετά το token βγαίνει από *My Account Settings → Web API Security Token*.
2. Marketplace/HACS → Custom repository → `https://github.com/aggelos250/aggelos250` (τύπος: Integration). Εναλλακτικά, αντιγράψτε τον φάκελο `custom_components/greek_energy_prices` στο `config/custom_components/`.
3. Κάντε επανεκκίνηση και προσθέστε το integration «Greek Dynamic Energy Prices».

## Παράδειγμα αυτοματισμού

```yaml
automation:
  - alias: Θερμοσίφωνας στις φθηνές ώρες
    triggers:
      - trigger: state
        entity_id: binary_sensor.greek_electricity_prices_cheap_hour_now
    actions:
      - action: >-
          {{ 'switch.turn_on' if trigger.to_state.state == 'on' else 'switch.turn_off' }}
        target:
          entity_id: switch.thermosifonas
```

## Ανάπτυξη

```bash
pip install -r requirements_test.txt
pytest
```

## Roadmap

- [ ] Δεδομένα κατανάλωσης από το portal μετρήσεων του ΔΕΔΔΗΕ
- [ ] Έτοιμα προφίλ χρεώσεων για τους μεγάλους παρόχους
- [ ] Βελτιστοποίηση μπαταρίας/φωτοβολταϊκών (net billing)
- [ ] Εναλλακτική πηγή: αποτελέσματα ΑΕΗ από το ΕΧΕ (HEnEx), χωρίς token

## Άδεια

MIT
