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

Τα ελληνικά δυναμικά τιμολόγια χρεώνουν την προμήθεια ως **Β × ΤΕΑ + Α**: ΤΕΑ είναι η τιμή της Αγοράς Επόμενης Ημέρας (μέσος όρος ώρας), Β ένας σταθερός συντελεστής (περίπου 1,2, απώλειες δικτύου) και Α μια σταθερή βασική τιμή του παρόχου.

```
τελική = (Β × ΤΕΑ + Α + ρυθμιζόμενες χρεώσεις) × (1 + ΦΠΑ)
```

### Έτοιμα προφίλ παρόχων

Στη ρύθμιση διαλέγετε τον πάροχό σας και τα Α και Β συμπληρώνονται αυτόματα. Μπορείτε να τα διορθώσετε πριν την αποθήκευση.

| Πάροχος – πρόγραμμα | Β | Α (€/kWh) | Πάγιο (€/μήνα) | Πηγή |
|---|---|---|---|---|
| ΔΕΗ – myHome Dynamic | 1,19 | 0,044 | 9,00 | [techmaniacs.gr](https://techmaniacs.gr/dei-myhome-dynamic-gia-idiotes-anakoinothike-to-neo-programma-ilektrikis-energeias/) |
| Protergia – Dynamic One Home | 1,2 | 0,035 ⚠️ | 9,90 | [protergia.gr](https://www.protergia.gr/en/home/electric-energy/dynamic-one-home/) |
| ZeniΘ – Power Home Flow | 1,2 | 0,100 | 15,00 | [zenith.gr](https://zenith.gr/el/for-the-home/electricity/power-home-flow/) |

Οι τιμές ελέγχθηκαν την 1/11/2026 από δημόσιες σελίδες. **Οι πάροχοι τις αλλάζουν, οπότε συγκρίνετε με το συμβόλαιό σας.** ⚠️ Για την Protergia η πηγή γράφει «35» χωρίς μονάδα. Το διαβάζουμε ως €/MWh.

Δεν περιλαμβάνονται ακόμα:
- **ΗΡΩΝ Happy Hour Home:** δίνει 3 δωρεάν ώρες τη μέρα, που αλλάζουν καθημερινά, και δεν βρήκαμε δημοσιευμένα Α και Β.
- **Enerwave, NRG** κ.λπ.: δεν βρήκαμε τα στοιχεία τους.

Αν έχετε κάποιον από αυτούς, βάλτε τις τιμές από το συμβόλαιό σας με την επιλογή «Άλλο / Χειροκίνητα». Προσθήκες και διορθώσεις στο `tariffs.py` είναι ευπρόσδεκτες.

Το **πάγιο** εμφανίζεται ως attribute και δεν μπαίνει στην τιμή ανά kWh.

### Ρυθμιζόμενες χρεώσεις

Οι **ρυθμιζόμενες χρεώσεις** είναι ίδιες για όλους τους παρόχους: δίκτυο ΔΕΔΔΗΕ/ΑΔΜΗΕ, ΥΚΩ (κλιμακωτή ανάλογα με την κατανάλωση), ΕΤΜΕΑΡ (0,017 €/kWh) και ΕΦΚ. Επειδή κάποιες εξαρτώνται από την κατανάλωσή σας, τις βάζετε ως ένα συνολικό ποσό ανά kWh, με βάση τον λογαριασμό σας.

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
- [x] Έτοιμα προφίλ χρεώσεων παρόχων (ΔΕΗ, Protergia, ZeniΘ)
- [ ] Περισσότεροι πάροχοι (ΗΡΩΝ, Enerwave, NRG …) και αυτόματη ενημέρωση των προφίλ
- [ ] Υπολογισμός ρυθμιζόμενων χρεώσεων ανά κλίμακα ΥΚΩ
- [ ] Βελτιστοποίηση μπαταρίας/φωτοβολταϊκών (net billing)
- [ ] Εναλλακτική πηγή: αποτελέσματα ΑΕΗ από το ΕΧΕ (HEnEx), χωρίς token

## Άδεια

MIT
